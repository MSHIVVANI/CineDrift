import time
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

options = uc.ChromeOptions()
# options.add_argument("--headless=new")  # For debugging, run with visible browser
driver = uc.Chrome(options=options)
movie_url = "https://letterboxd.com/film/the-dark-knight/reviews/by/activity/"
driver.get(movie_url)
time.sleep(5)
driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
time.sleep(2)

# Save the page source for inspection
with open("debug_page.html", "w", encoding="utf-8") as f:
    f.write(driver.page_source)

review_boxes_xpath = '//div[@data-tab="by-activity" and contains(@class,"is-active")]//div[contains(@class,"film-detail-content__reviews-pane-list")]/article'
try:
    WebDriverWait(driver, 20).until(
        EC.presence_of_all_elements_located((By.XPATH, review_boxes_xpath))
    )
    review_boxes = driver.find_elements(By.XPATH, review_boxes_xpath)
    print(f"Found {len(review_boxes)} review articles with XPath: {review_boxes_xpath}")
except Exception as e:
    print(f"Error finding review articles: {e}")

driver.quit()
