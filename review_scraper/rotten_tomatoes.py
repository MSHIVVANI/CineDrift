import time
import hashlib
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc
from supabase_utils import insert_review

def get_movie_id(movie_url):
    return hashlib.md5(movie_url.encode('utf-8')).hexdigest()

def close_consent_popup(driver):
    try:
        consent_btn = WebDriverWait(driver, 3).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(text(),'Accept')]"))
        )
        consent_btn.click()
        time.sleep(0.5)
    except Exception:
        pass

def click_load_more_shadow(driver):
    """Click the Load More button inside the Shadow DOM, if present."""
    try:
        rt_button = driver.find_element(By.CSS_SELECTOR, '#reviews rt-button')
        driver.execute_script("""
            let rtBtn = arguments[0];
            if(rtBtn && rtBtn.shadowRoot){
                let btn = rtBtn.shadowRoot.querySelector('button');
                if(btn) btn.click();
            }
        """, rt_button)
        return True
    except Exception:
        return False

def load_reviews_until(driver, min_reviews=200, max_attempts=30):
    review_containers_xpath = '//*[@id="reviews"]/div[1]/div'
    attempts = 0
    while attempts < max_attempts:
        review_containers = driver.find_elements(By.XPATH, review_containers_xpath)
        current_count = len(review_containers)
        if current_count >= min_reviews:
            break
        loaded = click_load_more_shadow(driver)
        if not loaded:
            break
        # Wait for new reviews to load, but don't sleep longer than needed
        for _ in range(15):
            time.sleep(0.25)
            new_count = len(driver.find_elements(By.XPATH, review_containers_xpath))
            if new_count > current_count:
                break
        attempts += 1

def extract_release_year(driver):
    try:
        release_date_elem = driver.find_element(By.XPATH, '//*[@id="main-page-content"]/div/aside/section/div[1]/ul/li[4]')
        release_date_text = release_date_elem.text.strip()
        match = re.search(r'(\d{4})', release_date_text)
        if match:
            return match.group(1)
    except Exception:
        pass
    return ""

def extract_review_rating_from_score_text(score_text, fresh_rotten=None):
    match = re.search(r'(\d+(\.\d+)?)/10', score_text)
    if match:
        num = float(match.group(1))
        return round(num / 2, 2)
    match = re.search(r'\b([A-F][+-]?)\b', score_text)
    if match:
        letter = match.group(1).upper()
        letter_map = {
            'A+': 5.0, 'A': 4.7, 'A-': 4.3,
            'B+': 4.0, 'B': 3.7, 'B-': 3.3,
            'C+': 3.0, 'C': 2.7, 'C-': 2.3,
            'D+': 2.0, 'D': 1.7, 'D-': 1.3,
            'F': 1.0
        }
        return letter_map.get(letter, 0.0)
    if fresh_rotten == "fresh":
        return 4.0
    elif fresh_rotten == "rotten":
        return 2.0
    else:
        return 0.0

def process_reviews(driver, movie_url, source_site):
    movie_name = movie_url.split("/m/")[1].split("/")[0].replace("_", " ").title()
    movie_release_year = extract_release_year(driver)
    movie_id = get_movie_id(movie_url)
    reviews_scraped = 0
    seen_reviews = set()

    # Load reviews until at least 200 are visible or no more can be loaded
    load_reviews_until(driver, min_reviews=200, max_attempts=30)

    review_containers_xpath = '//*[@id="reviews"]/div[1]/div'
    review_containers = driver.find_elements(By.XPATH, review_containers_xpath)
    total_reviews = len(review_containers)

    for idx, review_box in enumerate(review_containers, start=1):
        if reviews_scraped >= 200:
            break
        try:
            # Expand "Full Review" if available
            try:
                full_review_btn = review_box.find_element(By.XPATH, './div[2]/p[2]/a')
                driver.execute_script("arguments[0].click();", full_review_btn)
                time.sleep(0.05)
            except Exception:
                pass

            # Review text
            try:
                review_text = review_box.find_element(By.XPATH, './div[2]/p[1]').text.strip()
            except Exception:
                review_text = ""

            # Reviewer name
            try:
                reviewer_name = review_box.find_element(By.XPATH, './div[1]/div/a[1]').text.strip()
            except Exception:
                reviewer_name = ""

            # Review date
            try:
                review_date = review_box.find_element(By.XPATH, './div[2]/p[2]/span').text.strip()
            except Exception:
                review_date = ""

            # Score text (may contain numeric or letter grade)
            try:
                score_text = review_box.find_element(By.XPATH, './div[2]/p[2]').text.strip()
            except Exception:
                score_text = ""

            # Fresh/rotten icon
            try:
                icon = review_box.find_element(By.XPATH, './/span[contains(@class, "review-icon")]')
                icon_class = icon.get_attribute("class")
                if "fresh" in icon_class:
                    fresh_rotten = "fresh"
                elif "rotten" in icon_class:
                    fresh_rotten = "rotten"
                else:
                    fresh_rotten = None
            except Exception:
                fresh_rotten = None

            # Convert to star_rating
            star_rating = extract_review_rating_from_score_text(score_text, fresh_rotten)

            # Uniqueness
            review_hash = hashlib.md5((reviewer_name + review_text).encode('utf-8')).hexdigest()
            if review_hash in seen_reviews or not review_text:
                continue
            seen_reviews.add(review_hash)

            likes_count = 0

            data = {
                "movie_id": movie_id,
                "reviewer_name": reviewer_name,
                "movie_name": movie_name,
                "movie_release_year": movie_release_year,
                "review_date": review_date,
                "review_text": review_text,
                "star_rating": star_rating,
                "likes_count": likes_count,
                "source_site": source_site,
                "language": "english"
            }
            insert_review(data)
            reviews_scraped += 1

        except Exception as e:
            print(f"Error processing review {idx}: {e}")

    print(f"Completed {reviews_scraped} reviews for {movie_name}")
    return reviews_scraped

def scrape_rotten_tomatoes_reviews(movie_urls: list, source_site: str = "rottentomatoes"):
    options = uc.ChromeOptions()
    # Uncomment for speed in headless environments:
    # options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    driver = uc.Chrome(options=options)

    for movie_url in movie_urls:
        driver.get(movie_url)
        time.sleep(2)
        close_consent_popup(driver)
        print(f"\nStarting scraping for: {movie_url}")
        start_time = time.time()
        processed_count = process_reviews(driver, movie_url, source_site)
        print(f"Finished {processed_count} reviews in {time.time()-start_time:.1f}s")

    driver.quit()

if __name__ == "__main__":
    movie_urls = [
        "https://www.rottentomatoes.com/m/final_destination_bloodlines/reviews",
        "https://www.rottentomatoes.com/m/dune_part_two/reviews",
        "https://www.rottentomatoes.com/m/oppenheimer_2023/reviews"
    ]
    scrape_rotten_tomatoes_reviews(movie_urls)
