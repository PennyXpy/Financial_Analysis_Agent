import baostock as bs

print("🔍 正在测试 Baostock 登录...")

# 登录
lg = bs.login()
print(f"登录返回码: {lg.error_code}")
print(f"登录消息: {lg.error_msg}")

# 判断结果
if lg.error_code == '0':
    print("✅ Baostock 登录成功！")
else:
    print("❌ 登录失败，请检查网络或 Baostock 服务。")

# 登出
bs.logout()
print("🏁 已登出 Baostock。")

