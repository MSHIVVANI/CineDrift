from letterboxd import scrape_letterboxd_reviews

if __name__ == "__main__":
    movie_url = "https://letterboxd.com/film/the-dark-knight/reviews/by/activity/"
    scrape_letterboxd_reviews(movie_url, max_pages=3)
