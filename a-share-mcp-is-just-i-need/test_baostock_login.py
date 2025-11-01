import baostock as bs

print("🔍 Testing Baostock login...")

# Login
lg = bs.login()
print(f"Login return code: {lg.error_code}")
print(f"Login message: {lg.error_msg}")

# Check result
if lg.error_code == '0':
    print("✅ Baostock login successful!")
else:
    print("❌ Login failed. Please check your network or Baostock service status.")

# Logout
bs.logout()
print("🏁 Logged out from Baostock.")
