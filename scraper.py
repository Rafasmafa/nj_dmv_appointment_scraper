import time
import re
import os
import traceback

from datetime import datetime

from cached_property import cached_property
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from twilio.rest import Client
from selenium.webdriver.chrome.options import Options


class NjDmvScraper:
    """
    This class scrapes the NJ dmv appointment website for OUT OF STATE
    LICENSE TRANSFERS ONLY. To check for other appointments change self.base_url

    Parameters:
        cities: list of cities to check appointments for. (ex:['newark', 'wayne'] )
        search_months: list of months to check for open appointments. (ex:['May', 'June'] )

    Environment Variables:
        PHONE_NUMBER: a phone number to send texts to.
        TWILIO_ACCOUNT_SID: twilio account SID
        TWILIO_AUTH_TOKEN: twilio auth token
    """

    def __init__(self, cities: list[str], search_months: list[str]):
        self.cities = {city.title() for city in cities}
        self.search_months = search_months
        self.base_url = 'https://telegov.njportal.com/njmvc/AppointmentWizard/7'
        self.phone_number = os.getenv("PHONE_NUMBER")
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        self.twilio_client = Client(account_sid, auth_token)
        if not self.phone_number or not account_sid or not auth_token:
            raise Exception(
                'Ensure the following env vars are defined PHONE_NUMBER, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN')
        self.found_appts = {}
        for city in self.cities:
            self.found_appts[city] = []

    def run(self):
        """
        Check DMV appointments every minute until the program is killed
        """
        while True:
            try:
                self.check_open_appointments()
                time.sleep(30)
            except Exception:
                print(traceback.format_exc())
                self.chrome_driver.quit()

    def check_open_appointments(self):
        """
        Checks base url for open appointments within the cities and months
        that were given in the constructor.
        """
        for city in self.cities:
            self.chrome_driver.get(self.base_url)
            print(f'CHECKING APPOINTMENTS IN {city.title()}', flush=True)
            locations_div = self.chrome_driver.find_element(By.ID, "locationsDiv")
            city_nodes = locations_div.find_elements(By.CLASS_NAME, "text-capitalize")
            for city_node in city_nodes:
                current_city = city_node.find_element(By.TAG_NAME, 'span').text.split('\n')[0]
                if current_city == city and "Next Available:" in city_node.text:
                    appt_dt = self.get_next_appt_dt(city_node.text)
                    if self._is_valid_appointment(city, appt_dt):
                        print(f'FOUND APPOINTMENT: {city}', flush=True)
                        # click link to go to appointments page
                        # this is how we get the url to send via text
                        city_node.find_element(By.LINK_TEXT, "MAKE APPOINTMENT").click()
                        self.found_appts[city].append(appt_dt)
                        time.sleep(2)  # wait for page to load
                        self.send_message(current_city.title(),
                                          appt_dt.strftime("%m/%d/%Y %I:%M %p"),
                                          self.chrome_driver.current_url)
                        break

    def _is_valid_appointment(self, city: str, appt_dt: datetime) -> bool:
        """
        Helper function to determine the appointment date is in the search_months
        and if we have already found the appointment

        Parameters:
            city: a city name
            appt_dt: appointment datetime object
        """
        return (appt_dt.strftime("%B") in self.search_months and
                appt_dt not in self.found_appts.get(city, []))

    @staticmethod
    def get_next_appt_dt(city_node_text: str) -> datetime:
        """
        Parse out date from city node text using %m/%d/%Y %I:%M %p"
        pattern and convert it to a datetime object

        Parameters:
            city_node_text: text from the city node html
        """
        regex = r"(?<=Next Available:\s).+(?=\sMAKE APPOINTMENT)"
        dt_string = re.search(regex, city_node_text).group(0)
        return datetime.strptime(dt_string, "%m/%d/%Y %I:%M %p")

    def send_message(self, city_name: str, date: str, link: str):
        """
        Sends a text message to the phone number given set the environment variable PHONE_NUMBER.

        Parameters:
            city_name: city name of the appointment.
            date: date of the appointment.
            link: link to the appointment.
        """
        body = f"Open appointment in {city_name} on {date} \n {link}"
        self.twilio_client.messages.create(body=body, from_='+18166242060', to='+1' + self.phone_number)

    @cached_property
    def chrome_driver(self) -> webdriver.Chrome:
        """Setup and init chromedriver."""
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        s = Service(ChromeDriverManager().install())
        return webdriver.Chrome(service=s, options=chrome_options)


if __name__ == "__main__":
    cities = ['wayne']
    months = ['April', 'May']
    scraper = NjDmvScraper(cities, months)
    scraper.run()
