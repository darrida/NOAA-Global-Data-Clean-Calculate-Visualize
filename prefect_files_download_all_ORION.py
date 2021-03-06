##############################################################################
# Author: Ben Hammond
# Last Changed: 5/7/21
#
# REQUIREMENTS
# - Detailed dependencies in requirements.txt
# - Directly referenced:
#   - prefect, bs4, requests
#
# - Infrastructure:
#   - Prefect: Script is registered as a Prefect flow with api.prefect.io
#     - Source: https://prefect.io
#
# DESCRIPTION
# - Uses requests and bs4 to webscrape a NOAA web page containing temperature data (goes back to 1929)
#   - Source: https://www.ncei.noaa.gov/data/global-summary-of-the-day/access/
# - Uses requests to download the files and store them on a local server
#   - Local files are in the same directory structure as the website (individual site files
#     stored in directories for each year)
# - Includes the following features (to assist with handling the download of 538,000 [34gb] csv files):
#   - Continue Downloading: If the download is interrupted, the script can pick up where it left off
#   - If caught up with downloads it downloads the current year again (refresh files that are updated everyday)
##############################################################################

# PyPI
from prefect import task, flow
from prefect.executors import DaskExecutor
from bs4 import BeautifulSoup as BS
import requests

# Standard
from pathlib import Path
import os
import re


@task
def find_highest_year(url: str, data_dir):
    year_folders = os.listdir(path=data_dir)
    print(year_folders)
    if year_folders:
        return max(year_folders)
    else:
        return 0


@task
def build_url(base_url, year=""):
    return f"{base_url}/{year}"


@task
def query_cloud_csvs(url: str, year: int) -> set:
    response = requests.get(url)
    parsed_html = BS(response.content, "html.parser")
    csv_cloud_set = set()
    for item in parsed_html.find_all("a"):
        if ".csv" in item.get_text():
            csv_cloud_set.add(item.get_text())
    return csv_cloud_set


@task
def query_local_csvs(year: int, data_dir: str) -> set:
    csv_local_set = set()
    data_dir = Path(data_dir)
    csv_folder = (data_dir / str(year)).rglob("*.csv")
    csv_local_list = [x for x in csv_folder]
    for i in csv_local_list:
        csv_local_set.add(str(i).split("/")[-1])
    return csv_local_set


@task
def query_diff_local_cloud(local_set: set, cloud_set: set) -> set:
    diff_set = cloud_set.difference(local_set)
    if diff_set:
        print(f"{len(diff_set)} new data files available for download.")
    else:
        print(f"No new data files for this run.")
    diff_l = list(diff_set)
    return diff_l


@task
def download_new_csvs(url: str, year: int, diff_set: set, data_dir: str) -> bool:
    if int(year) > 0:
        count = 0
        data_dir = Path(data_dir)
        download_path = data_dir / str(year)
        if os.path.exists(download_path) == False:
            Path(download_path).mkdir(parents=True, exist_ok=True)
        for i in diff_set:
            if count <= 1000:
                try:
                    download_url = url + "/" + i
                    print(download_url)
                    result = requests.get(download_url)
                    file_path = Path(data_dir / year / i)
                    open(file_path, "wb").write(result.content)
                except requests.exceptions.InvalidURL:
                    print("Bad url", i)
            count += 1
        if count <= 2000:
            return True
    elif year == 0:
        return True


@task
def find_new_year(url: str, next_year: bool, year: int, data_dir: str):
    if next_year:
        response = requests.get(url)
        parsed_html = BS(response.content, "html.parser")
        cloud_year_set = set()
        for item in parsed_html.find_all("a"):
            cloud_year = item.get_text().replace("/", "")
            cloud_year_set.add(cloud_year)
        cloud_year_set = [x for x in cloud_year_set if re.search(r"\d\d\d\d", x)]
        cloud_year_set = sorted(cloud_year_set, reverse=True)
        if year == 0:
            year = cloud_year_set[-1]
        else:
            for i in sorted(cloud_year_set):
                if int(i) > int(year):
                    year = i
                    break
        data_dir = Path(data_dir)
        download_path = data_dir / str(year)
        if os.path.exists(download_path) == False:
            Path(download_path).mkdir(parents=True, exist_ok=True)
        print("STATUS => new year:", year)
        return year
    print("STATUS => current year not finished.")


# def create_a_function(*args, **kwargs):

#     def function_template(*args, **kwargs):
#         func_str = ''
#         for data_l in data_lists:
#             func_str += """download_new_csvs(url=t2_url, year=t1_year, diff_set=t5_diff_l, data_dir=data_dir)\n"""
#         return func_str

#     return function_template

# my_new_function = create_a_function()


@flow(executor=DaskExecutor())
def parallel_flow():
    base_url = "https://www.ncei.noaa.gov/data/global-summary-of-the-day/access/"
    data_dir = str(Path("./local_data/noaa_temp_downloads"))

    t1_year = find_highest_year(url=base_url, data_dir=data_dir)
    t2_url = build_url(base_url=base_url, year=t1_year)
    t3_cset = query_cloud_csvs(url=t2_url, year=t1_year)
    t4_lset = query_local_csvs(year=t1_year, data_dir=data_dir)
    t5_diff_l = query_diff_local_cloud(local_set=t4_lset, cloud_set=t3_cset)
    t6_next = download_new_csvs(url=t2_url, year=t1_year, diff_set=t5_diff_l, data_dir=data_dir)
    return find_new_year(url=base_url, next_year=t6_next, year=t1_year, data_dir=data_dir)


if __name__ == "__main__":
    state = parallel_flow()
