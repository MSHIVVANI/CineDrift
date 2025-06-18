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
        consent_btn = WebDriverWait(driver, 5).until(
            EC.element_to_be_clickable((By.XPATH,
                "//button[contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'accept') or contains(translate(text(),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'agree')]"
            ))
        )
        consent_btn.click()
        time.sleep(1)
    except Exception:
        pass

def scrape_letterboxd_reviews(movie_urls: list, source_site: str = "letterboxd"):
    options = uc.ChromeOptions()
    # Uncomment for debugging
    # options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    driver = uc.Chrome(options=options)

    for movie_url in movie_urls:
        driver.get(movie_url)
        time.sleep(3)
        close_consent_popup(driver)

        try:
            movie_name = WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.XPATH, '//*[@id="content"]/div/div/section/header/div/h1/a'))
            ).text
            movie_release_year = driver.find_element(By.XPATH, '//*[@id="content"]/div/div/section/header/div/h1/small/a').text
        except Exception as e:
            print(f"Failed to extract movie name or release year for {movie_url}: {e}")
            continue

        movie_id = get_movie_id(movie_url)
        reviews_scraped = 0

        review_boxes_xpath = '//*[@id="content"]/div/div/section/div[3]/div'
        next_button_xpath = '//*[@id="content"]/div/div/section/div[4]/div[2]/a'

        while reviews_scraped < 200:
            try:
                WebDriverWait(driver, 20).until(
                    EC.presence_of_all_elements_located((By.XPATH, review_boxes_xpath))
                )
                review_boxes = driver.find_elements(By.XPATH, review_boxes_xpath)
                print(f"Scraping {movie_name}: Page reviews found: {len(review_boxes)}")
            except Exception as e:
                print(f"Error finding review boxes: {e}")
                break

            for box in review_boxes:
                if reviews_scraped >= 200:
                    break
                try:
                    reviewer_name = box.find_element(By.XPATH, './/strong[contains(@class,"displayname")]').text
                    review_date = box.find_element(By.XPATH, './/time').text

                    try:
                        more_btn = box.find_element(By.XPATH, './/a[contains(@class,"more-link")]')
                        driver.execute_script("arguments[0].click();", more_btn)
                        time.sleep(0.3)
                    except Exception:
                        pass

                    review_text = box.find_element(By.XPATH, './/div[contains(@class,"js-review-body")]//p').text

                    try:
                        rating_span = box.find_element(By.XPATH, './/span[contains(@class,"rating")]')
                        class_str = rating_span.get_attribute("class")
                        match = re.search(r'rated-(\d+)', class_str)
                        star_rating = float(match.group(1)) / 2 if match else 0.0
                    except Exception:
                        star_rating = 0.0

                    try:
                        likes_span = box.find_element(By.XPATH, './/span[contains(@class,"_count_")]')
                        likes_text = likes_span.text.strip()
                        likes_count = int(''.join(filter(str.isdigit, likes_text))) if ''.join(filter(str.isdigit, likes_text)) else 0
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
                    insert_review(data)
                    reviews_scraped += 1

                except Exception as e:
                    print(f"Error extracting review: {e}")
                    print("Review HTML:", box.get_attribute('outerHTML'))
                    continue

            if reviews_scraped >= 200:
                print(f"Collected 200 reviews for {movie_name}. Moving to next movie.")
                break

            try:
                next_button = driver.find_element(By.XPATH, next_button_xpath)
                driver.execute_script("arguments[0].scrollIntoView();", next_button)
                time.sleep(0.5)
                if "disabled" in next_button.get_attribute("class"):
                    print("Next button is disabled. No more pages.")
                    break
                next_button.click()
                time.sleep(2)
            except Exception:
                print("No more pages or next button not found.")
                break

    try:
        driver.quit()
    except Exception:
        pass

if __name__ == "__main__":
    movie_urls = [
        "https://letterboxd.com/film/the-substance/reviews/by/activity/",
        "https://letterboxd.com/film/kill-bill-vol-1/reviews/by/activity/",
        "https://letterboxd.com/film/deadpool-wolverine/reviews/by/activity/",
        "https://letterboxd.com/film/arrival-2016/reviews/by/activity/",
        "https://letterboxd.com/film/past-lives/reviews/by/activity/",
        "https://letterboxd.com/film/the-devil-wears-prada/reviews/by/activity/",
        "https://letterboxd.com/film/moonlight-2016/reviews/by/activity/",
        "https://letterboxd.com/film/the-social-network/reviews/by/activity/",
        "https://letterboxd.com/film/memento/reviews/by/activity/",
        "https://letterboxd.com/film/pride-prejudice/reviews/by/activity/"
    ]
    scrape_letterboxd_reviews(movie_urls)
