import time
import hashlib
import re
from datetime import datetime, timedelta
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import undetected_chromedriver as uc
from supabase_utils import insert_review

def get_movie_id(movie_url):
    return hashlib.md5(movie_url.encode('utf-8')).hexdigest()

def close_consent_popup(driver):
    try:
        consent_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH, "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'agree')]"))
        )
        consent_btn.click()
        time.sleep(1)
    except Exception:
        pass

def parse_relative_date(date_str):
    date_str = date_str.lower().strip()
    now = datetime.now()
    if "day" in date_str:
        match = re.search(r'(\d+) day', date_str)
        days = int(match.group(1)) if match else 1
        return (now - timedelta(days=days)).strftime('%Y-%m-%d')
    elif "hour" in date_str:
        match = re.search(r'(\d+) hour', date_str)
        hours = int(match.group(1)) if match else 1
        return (now - timedelta(hours=hours)).strftime('%Y-%m-%d')
    elif "minute" in date_str:
        match = re.search(r'(\d+) minute', date_str)
        minutes = int(match.group(1)) if match else 1
        return (now - timedelta(minutes=minutes)).strftime('%Y-%m-%d')
    elif "just now" in date_str or "few seconds" in date_str:
        return now.strftime('%Y-%m-%d')
    else:
        return date_str

def wait_for_more_reviews(driver, review_xpath, previous_count, timeout=60):
    """Wait until more reviews are loaded (number of elements increases), up to 60 seconds."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        current_count = len(driver.find_elements(By.XPATH, review_xpath))
        if current_count > previous_count:
            return True
        time.sleep(0.5)
    return False

def scrape_bookmyshow_reviews(movie_urls: list, source_site: str = "bookmyshow"):
    options = uc.ChromeOptions()
    # options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    driver = uc.Chrome(options=options)

    for movie_url in movie_urls:
        driver.get(movie_url)
        time.sleep(3)
        close_consent_popup(driver)

        # Movie name
        try:
            movie_name = WebDriverWait(driver, 10).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="super-container"]/div[1]/div/div/div[1]'))
            ).text.strip()
        except Exception as e:
            print(f"Failed to extract movie name for {movie_url}: {e}")
            continue

        # Release year
        try:
            release_date_elem = driver.find_element(By.XPATH, '//*[@id="super-container"]/div[1]/div/div/section[1]/div[1]/div[1]/div[2]/span')
            release_date_text = release_date_elem.text.strip()
            match = re.search(r'(\d{4})', release_date_text)
            movie_release_year = match.group(1) if match else ""
        except Exception:
            movie_release_year = ""

        movie_id = get_movie_id(movie_url)
        reviews_scraped = 0
        seen_reviews = set()
        batch = []

        review_boxes_xpath = '//*[@id="super-container"]/div[1]/div/div/section[3]/div[1]/div[3]/div'

        # Wait for the first batch of reviews to load
        try:
            WebDriverWait(driver, 10).until(
                EC.presence_of_all_elements_located((By.XPATH, review_boxes_xpath))
            )
        except Exception as e:
            print(f"No reviews found for {movie_name}: {e}")
            continue

        last_review_count = 0
        scroll_attempts = 0

        while reviews_scraped < 200:
            review_boxes = driver.find_elements(By.XPATH, review_boxes_xpath)
            total_reviews = len(review_boxes)

            # Scrape only new reviews
            for idx in range(last_review_count + 1, total_reviews + 1):
                if reviews_scraped >= 200:
                    break
                try:
                    box_xpath = f'{review_boxes_xpath}[{idx}]'
                    box = driver.find_element(By.XPATH, box_xpath)

                    # Review text
                    try:
                        review_text = box.find_element(By.XPATH, './div[1]/div/p').text.strip()
                    except Exception:
                        review_text = ""

                    reviewer_name = "user"

                    # Review date
                    try:
                        review_date_str = box.find_element(By.XPATH, './div[2]/div[2]/span').text.strip()
                        review_date = parse_relative_date(review_date_str)
                    except Exception:
                        review_date = ""

                    # Star rating (out of 10, convert to 5)
                    try:
                        rating_xpath = f'{box_xpath}/div[1]/section/div[2]/div'
                        rating_text = driver.find_element(By.XPATH, rating_xpath).text.strip()
                        rating_match = re.search(r'(\d+(\.\d+)?)/10', rating_text)
                        if rating_match:
                            star_rating = float(rating_match.group(1)) / 2
                        else:
                            star_rating = 0.0
                    except Exception:
                        star_rating = 0.0

                    # Likes count
                    try:
                        likes_xpath = f'{box_xpath}/div[2]/div[1]/button[1]/span'
                        likes_text = driver.find_element(By.XPATH, likes_xpath).text.strip()
                        likes_count = int(''.join(filter(str.isdigit, likes_text))) if likes_text else 0
                    except Exception:
                        likes_count = 0

                    review_hash = hashlib.md5((reviewer_name + review_text).encode('utf-8')).hexdigest()
                    if review_hash in seen_reviews or not review_text:
                        continue
                    seen_reviews.add(review_hash)

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
                    batch.append(data)
                    reviews_scraped += 1

                    if len(batch) == 20:
                        for review in batch:
                            insert_review(review)
                        batch = []

                except Exception as e:
                    print(f"Error extracting review {idx}: {e}")
                    continue

            if reviews_scraped >= 200:
                print(f"Collected 200 reviews for {movie_name}. Moving to next movie.")
                break

            if total_reviews == last_review_count:
                # No new reviews loaded, try scrolling
                scroll_attempts += 1
                driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
                # Wait up to 60s for more reviews to load
                loaded = wait_for_more_reviews(driver, review_boxes_xpath, last_review_count, timeout=60)
                if not loaded or scroll_attempts > 5:
                    print(f"No more reviews loaded after scrolling for {movie_name}.")
                    break
            else:
                scroll_attempts = 0
                last_review_count = total_reviews
                time.sleep(3)  # Allow more reviews to load

        # Insert any remaining reviews in the last batch
        if batch:
            for review in batch:
                insert_review(review)

        print(f"Scraped {reviews_scraped} reviews for {movie_name}")

    try:
        driver.quit()
    except Exception:
        pass

if __name__ == "__main__":
    movie_urls = [
        "https://in.bookmyshow.com/movies/chennai/thug-life/ET00375421/user-reviews",
        # Add more URLs as needed
    ]
    scrape_bookmyshow_reviews(movie_urls)
