import os
import torch
import pandas as pd
import numpy as np
from datasets import Dataset
from sklearn.model_selection import train_test_split
from transformers import (
    AutoTokenizer, 
    AutoModelForCausalLM,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling
)
from peft import (
    LoraConfig,
    get_peft_model,
    TaskType,
    prepare_model_for_kbit_training
)
import warnings
warnings.filterwarnings("ignore")

# Set device
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
print(f"Using device: {device}")

# Data preprocessing function
def load_and_preprocess_data(csv_path):
    """Load and preprocess data"""
    print("Loading data...")
    df = pd.read_csv(csv_path)[:1000]  # limit number of samples
    
    # Filter valid data
    df = df[df['Lsa_summary'].notna() & df['risk_deepseek'].notna()]
    df = df[df['risk_deepseek'] != 0]  # remove invalid risk labels
    
    print(f"Valid data count: {len(df)}")
    print(f"Risk distribution: {df['risk_deepseek'].value_counts().sort_index()}")
    
    return df

def create_prompt_template(text, risk_score, stock_symbol="STOCK"):
    """Create training prompt template – using risk assessment format"""
    # Use the same conversation format as in risk_deepseek_deepinfra.py
    system_prompt = (
        "Forget all your previous instructions. You are a financial expert "
        "specializing in risk assessment for stock recommendations. Based on a specific stock, "
        "provide a risk score from 1 to 5, where: 1 indicates very low risk, "
        "2 indicates low risk, 3 indicates moderate risk (default if the news lacks any clear indication of risk), "
        "4 indicates high risk, and 5 indicates very high risk. One summarized news item will be passed in each time. "
        "Provide the score in the format shown below in the assistant's response."
    )
    
    # Construct user input
    user_content = f"News to Stock Symbol -- {stock_symbol}: {text}"
    
    # Build full conversation
    conversation = f"""System: {system_prompt}

User: News to Stock Symbol -- AAPL: Apple (AAPL) increases 22%
Assistant: 3

User: News to Stock Symbol -- AAPL: Apple (AAPL) price decreased 30%
Assistant: 4

User: News to Stock Symbol -- AAPL: Apple (AAPL) announced iPhone 15
Assistant: 3

User: {user_content}
Assistant: {risk_score}"""
    
    return conversation

def prepare_dataset(df, tokenizer, max_length=512):
    """Prepare the training dataset"""
    print("Preparing dataset...")
    
    texts = []
    labels = []
    
    for _, row in df.iterrows():
        text = row['Lsa_summary']
        risk_score = int(row['risk_deepseek'])
        stock_symbol = row.get('Stock_symbol', 'STOCK')  # get stock symbol, default if missing
        
        if pd.isna(text) or text == '':
            continue
            
        prompt = create_prompt_template(text, risk_score, stock_symbol)
        texts.append(prompt)
        labels.append(risk_score)
    
    # Split into training and validation sets (80% train, 20% validation)
    train_texts, eval_texts, train_labels, eval_labels = train_test_split(
        texts, labels, test_size=0.2, random_state=42, stratify=None
    )
    
    print(f"Training set size: {len(train_texts)}")
    print(f"Validation set size: {len(eval_texts)}")
    
    # Create training dataset
    train_dataset = Dataset.from_dict({
        'text': train_texts,
        'label': train_labels
    })
    
    # Create validation dataset
    eval_dataset = Dataset.from_dict({
        'text': eval_texts,
        'label': eval_labels
    })
    
    def tokenize_function(examples):
        tokenized = tokenizer(
            examples['text'],
            truncation=True,
            padding='max_length',
            max_length=max_length,
            return_tensors='pt'
        )
        # For language modeling, labels are the same as input_ids
        tokenized['labels'] = tokenized['input_ids'].clone()
        return tokenized
    
    # Tokenize both training and validation datasets
    train_tokenized = train_dataset.map(
        tokenize_function,
        batched=True,
        remove_columns=train_dataset.column_names
    )
    
    eval_tokenized = eval_dataset.map(
        tokenize_function,
        batched=True,
        remove_columns=eval_dataset.column_names
    )
    
    return train_tokenized, eval_tokenized

def create_model_and_tokenizer():
    """Create model and tokenizer"""
    print("Loading model and tokenizer...")
    
    model_name = "/root/code/Finance/Qwen"
    
    # Load tokenizer
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    
    # Load model
    model = AutoModelForCausalLM.from_pretrained(
        model_name,
        torch_dtype=torch.float16,
        device_map="auto",
        trust_remote_code=True
    )
    
    # Prepare model for LoRA fine-tuning
    model = prepare_model_for_kbit_training(model)
    
    # LoRA configuration
    lora_config = LoraConfig(
        task_type=TaskType.CAUSAL_LM,
        r=16,  # LoRA rank
        lora_alpha=32,  # LoRA alpha
        lora_dropout=0.1,
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        bias="none",
    )
    
    # Apply LoRA
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    
    return model, tokenizer

def train_model(model, tokenizer, train_dataset, eval_dataset, output_dir="./qwen_risk_model"):
    """Train the model"""
    print("Starting training...")
    
    # Training arguments
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=3,
        per_device_train_batch_size=4,
        gradient_accumulation_steps=4,
        warmup_steps=100,
        learning_rate=2e-5,
        fp16=True,
        logging_steps=50,
        save_steps=500,
        eval_steps=500,
        eval_strategy="steps",
        save_strategy="steps",
        load_best_model_at_end=True,
        metric_for_best_model="eval_loss",
        greater_is_better=False,
        # report_to=None,  # disable reporting tools like wandb
        dataloader_pin_memory=False,
        remove_unused_columns=False,
    )
    
    # Data collator
    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False,
    )
    
    # Create Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        data_collator=data_collator,
        tokenizer=tokenizer,
    )
    
    # Start training
    trainer.train()
    
    # Save model
    trainer.save_model()
    tokenizer.save_pretrained(output_dir)
    print(f"Model saved to: {output_dir}")

def main():
    """Main function"""
    # Data path
    csv_path = "risk_nasdaq/risk_deepseek_cleaned_nasdaq_news_full.csv"
    
    # Load and preprocess data
    df = load_and_preprocess_data(csv_path)
    
    # Create model and tokenizer
    model, tokenizer = create_model_and_tokenizer()
    
    # Prepare dataset
    train_dataset, eval_dataset = prepare_dataset(df, tokenizer)
    
    # Train model
    train_model(model, tokenizer, train_dataset, eval_dataset)
    
    print("Training complete!")

if __name__ == "__main__":
    main()
