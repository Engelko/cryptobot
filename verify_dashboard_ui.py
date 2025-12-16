from playwright.sync_api import sync_playwright

def verify_dashboard():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            print("Navigating to dashboard...")
            page.goto("http://localhost:8501")

            # Wait for the dashboard to load
            page.wait_for_selector("text=Project Antigravity: Mission Control")
            print("Dashboard loaded.")

            # Allow some time for sidebar balance to fetch (async)
            page.wait_for_timeout(3000)

            page.screenshot(path="/home/jules/verification/dashboard_main.png")
            print("Screenshot main saved.")

            # Click on 'System' tab
            print("Clicking System tab...")
            page.get_by_role("tab", name="System").click()
            page.wait_for_selector("text=System Health")
            page.screenshot(path="/home/jules/verification/dashboard_system.png")
            print("Screenshot system saved.")

            # Click on 'Help' tab
            print("Clicking Help tab...")
            page.get_by_role("tab", name="Help").click()
            page.wait_for_selector("text=How to use Project Antigravity")
            page.screenshot(path="/home/jules/verification/dashboard_help.png")
            print("Screenshot help saved.")

        except Exception as e:
            print(f"Error: {e}")
        finally:
            browser.close()

if __name__ == "__main__":
    verify_dashboard()
