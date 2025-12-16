import asyncio
from antigravity.audit import audit
from antigravity.logging import configure_logging
import os

async def main():
    configure_logging()
    
    print("X-Testing Audit Log...")
    
    # 1. Write Audit Entry
    test_msg = "SECURITY_TEST_ENTRY_12345"
    audit.log_event("TEST", test_msg, "INFO")
    
    # 2. Verify File Exists and Contains Content
    if os.path.exists(audit.log_file):
        print(f"X-Audit File Found: {audit.log_file}")
        with open(audit.log_file, "r") as f:
            content = f.read()
            if test_msg in content:
                 print("X-Verification Successful: Test entry found in log.")
                 print(f"X-Latest Entry: {content.splitlines()[-1]}")
            else:
                 print("!! Test entry NOT found in log.")
    else:
        print("!! Audit file NOT found.")
        
    # 3. Check Firewall (UFW) - Informational, likely needs sudo so might fail
    print("X-Checking Firewall Status...")
    try:
        # Running as non-root, just checking if command exists usually
        # But let's try to just cat info if possible or use netstat to see open ports
        stream = os.popen('netstat -tuln | grep 8501')
        output = stream.read()
        if output:
            print(f"X-Streamlit Port 8501 Open: {output.strip()}")
        else:
            print("!! Port 8501 not seen in netstat (Might be listening on IPv6 or blocked?)")
    except Exception as e:
        print(f"!! Firewall check error: {e}")

    print("X-Test Complete")

if __name__ == "__main__":
    asyncio.run(main())
