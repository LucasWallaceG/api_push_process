from selenium import webdriver
from selenium.webdriver.firefox.options import Options

def create_driver(*, headless: bool = True, page_load_strategy: str = "eager"):

    opts = Options()
    if headless:
        opts.add_argument("--headless")
    opts.page_load_strategy = page_load_strategy

    driver = webdriver.Firefox(options=opts)

    driver.set_page_load_timeout(60)
    driver.implicitly_wait(0)
    return driver
