from playwright.sync_api import sync_playwright
import time

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": 1920, "height": 1080})

    # Navigate to Neo4j Browser
    page.goto("http://localhost:7474", timeout=30000)
    time.sleep(5)

    # Fill in password and connect
    password_input = page.locator('input[type="password"]')
    password_input.fill("password")
    time.sleep(1)

    # Click the submit button on the connection form
    connect_button = page.get_by_test_id("connection-form-submit")
    connect_button.click()
    time.sleep(8)

    # Close all "Remove frame" buttons to dismiss welcome and connect frames
    remove_buttons = page.locator('button[aria-label="Remove frame"]')
    count = remove_buttons.count()
    for i in range(count - 1, -1, -1):
        try:
            remove_buttons.nth(i).click()
            time.sleep(0.5)
        except:
            pass
    time.sleep(1)

    # Click on the main editor
    editor = page.get_by_test_id("main-editor")
    editor.click()
    time.sleep(1)

    # Type the query
    page.keyboard.press("Control+a")
    time.sleep(0.3)
    page.keyboard.type("MATCH (n) RETURN n")
    time.sleep(1)

    # Run the query with Ctrl+Enter
    page.keyboard.press("Control+Enter")
    time.sleep(20)

    # Take the final screenshot (no expand - shows sidebar with DB info)
    page.screenshot(path="neo4j_graph.png")
    print("Graph screenshot saved!")

    browser.close()
