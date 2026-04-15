import os
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
import uuid
import logging


def get_list_from_html(url_main,dnsserver:str=""):
    directory = "task_tmp"
    if not os.path.exists(directory):
        os.makedirs(directory)
    else:
        for filename in os.listdir(directory):
            if filename.endswith('.txt'):
                file_path = os.path.join(directory, filename)
                mod_time = os.path.getmtime(file_path)
                current_time = time.time()
                if (current_time - mod_time) > 600:
                    os.remove(file_path)

    fileurllist = f"{directory}/{uuid.uuid4()}.txt"
    user_agent = 'Mozilla/5.0 (Windows NT 6.1; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/99.0.4844.51 Safari/537.36'
    headers = {'User-Agent': user_agent}
    response = None

    try:
        response = requests.get(url_main, headers=headers, timeout=(5, 5),verify=False)
        response.raise_for_status()
    except requests.exceptions.HTTPError as error:
        logging.error(f"HTTP Error: {error}")
    except requests.exceptions.ConnectionError as error:
        logging.error(f"Connection Error: {error}")
    except requests.exceptions.Timeout as error:
        logging.error(f"Timeout Error: {error}")
    except requests.exceptions.RequestException as error:
        logging.error(f"Request Exception: {error}")
    else:
        logging.debug(f"Response Status Code: {response.status_code}")

    if response is None:
        with open(fileurllist, "w", encoding="UTF-8") as f:
            f.write(f'{url_main}\n')
            return fileurllist
    else:
        for resp in response.history:
            logging.debug(f"{resp.status_code} {resp.url}")
        final_url = response.url
        default_pre = "http:" if not final_url.startswith('https:') else "https:"
        base_url = final_url if final_url.endswith('/') else final_url + '/'
        with open(fileurllist, "w", encoding="UTF-8") as f:
            f.write(f'{url_main}\n')
            soup = BeautifulSoup(response.text, 'html.parser')
            for tag in soup.find_all(['img', 'link', 'script']):
                url = None
                if tag.name == 'img':
                    url = tag.get('src')
                elif tag.name == 'link' and tag.get('rel') == ['stylesheet']:
                    url = tag.get('href')
                elif tag.name == 'script':
                    url = tag.get('src')

                if url:
                    full_url=""
                    logging.debug(f"Original URL: {url}")
                    if url.startswith(('http:', 'https:')):
                        full_url = url
                    elif url.startswith('//'):
                        full_url = default_pre + url
                    elif url.startswith('data'):
                        pass
                    else:
                        full_url = urljoin(base_url, url)
                    logging.debug(f"Full URL: {full_url}")
                    f.write(f'{full_url}\n')
        return fileurllist