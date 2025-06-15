import time
import hashlib
import re
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
import undetected_chromedriver as uc
from supabase_utils import insert_review

def get_movie_id(movie_url):
    return hashlib.md5(movie_url.encode('utf-8')).hexdigest()

def close_consent_popup(driver):
    try:
        consent_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH,
                "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'agree')]"
            ))
        )
        consent_btn.click()
        time.sleep(1)
    except Exception:
        pass

def click_all_button(driver):
    all_button_xpath = '//*[@id="__next"]/main/div/section/div/section/div/div[1]/section[1]/div[3]/div/span[2]/button'
    try:
        all_button = WebDriverWait(driver, 10).until(
            EC.element_to_be_clickable((By.XPATH, all_button_xpath))
        )
        all_button.click()
        time.sleep(2)
    except Exception as e1:
        try:
            all_button = driver.find_element(By.XPATH, all_button_xpath)
            all_button.send_keys(Keys.ENTER)
            time.sleep(2)
        except Exception as e2:
            try:
                driver.execute_script("arguments[0].focus(); arguments[0].click();", all_button)
                time.sleep(2)
            except Exception as e3:
                print(f"Could not click 'All' button: {e1} | {e2} | {e3}")

def extract_release_year_from_title(title):
    # Extracts year from "Movie Name (1994) - IMDb" or similar
    match = re.search(r"\((\d{4})\)", title)
    return match.group(1) if match else ""

def scrape_imdb_reviews(movie_urls: list, source_site: str = "imdb"):
    options = uc.ChromeOptions()
    # options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    driver = uc.Chrome(options=options)

    for movie_url in movie_urls:
        driver.get(movie_url)
        time.sleep(3)
        close_consent_popup(driver)
        click_all_button(driver)

        try:
            # Movie name from the h1 title
            movie_name = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, '//h1[contains(@data-testid, "hero-title-block__title")]'))
            ).text
            # Release year from the page title
            movie_release_year = extract_release_year_from_title(driver.title)
        except Exception as e:
            try:
                movie_name = driver.title.split("-")[0].strip()
                movie_release_year = extract_release_year_from_title(driver.title)
            except Exception:
                print(f"Failed to extract movie name or release year for {movie_url}: {e}")
                continue

        movie_id = get_movie_id(movie_url)
        reviews_scraped = 0
        seen_reviews = set()
        batch = []

        base_xpath = '//*[@id="__next"]/main/div/section/div/section/div/div[1]/section[1]/article'
        review_index = 1

        while reviews_scraped < 200:
            review_xpath = f"{base_xpath}[{review_index}]"
            try:
                box = WebDriverWait(driver, 5).until(
                    EC.presence_of_element_located((By.XPATH, review_xpath))
                )
            except Exception:
                print(f"No more reviews found after {reviews_scraped} unique reviews.")
                break

            try:
                # Star rating (out of 10, convert to 0-5)
                try:
                    star_xpath = f'{review_xpath}/div[1]/div[1]/div[1]/span/span[1]'
                    score_element = driver.find_element(By.XPATH, star_xpath)
                    score = score_element.text.strip()
                    star_rating = float(score) / 2
                except Exception:
                    star_rating = 0.0

                # Reviewer name
                try:
                    reviewer_xpath = f'{review_xpath}/div[2]/ul/li[1]/a'
                    reviewer_name = driver.find_element(By.XPATH, reviewer_xpath).text.strip()
                except Exception:
                    reviewer_name = ""

                # Review date
                try:
                    date_xpath = f'{review_xpath}/div[2]/ul/li[2]'
                    review_date = driver.find_element(By.XPATH, date_xpath).text.strip()
                except Exception:
                    review_date = ""

                # Expand long review if button exists
                try:
                    expand_button_xpath = f'{review_xpath}/div[1]/div[1]/div[3]/button'
                    expand_button = driver.find_element(By.XPATH, expand_button_xpath)
                    driver.execute_script("arguments[0].click();", expand_button)
                    time.sleep(0.2)
                except Exception:
                    pass

                # Review text (always use the div you specified)
                try:
                    text_xpath = f'{review_xpath}/div[1]/div[1]/div[3]/div/div/div'
                    review_text = driver.find_element(By.XPATH, text_xpath).text.strip()
                except Exception:
                    review_text = ""

                # Unique hash for reviewer+review
                review_hash = hashlib.md5((reviewer_name + review_text).encode('utf-8')).hexdigest()
                if review_hash in seen_reviews or not review_text.strip():
                    review_index += 1
                    continue
                seen_reviews.add(review_hash)

                # Likes count ("X out of Y found this helpful")
                try:
                    helpfulness = box.find_element(By.XPATH, './/div[contains(@class,"actions")]/span').text
                    likes_count = int(helpfulness.split(" out of ")[0].replace(",", "").strip())
                except Exception:
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
                batch.append(data)
                reviews_scraped += 1

                # Insert in batches of 20
                if len(batch) == 20:
                    for review in batch:
                        insert_review(review)
                    batch = []

            except Exception as e:
                print(f"Error extracting review {review_index}: {e}")
                print("Review HTML:", box.get_attribute('outerHTML'))

            review_index += 1

        # Insert any remaining reviews in the last batch
        if batch:
            for review in batch:
                insert_review(review)

        print(f"Scraped {reviews_scraped} unique reviews for {movie_name}")

    try:
        driver.quit()
    except Exception:
        pass

if __name__ == "__main__":
    movie_urls = [
        "https://www.imdb.com/title/tt0111161/reviews/?ref_=tt_ururv_sm"
    ]
    scrape_imdb_reviews(movie_urls)
