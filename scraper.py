import time
import re
import os
import smtplib

from datetime import date, datetime
from selenium import webdriver
from drivers.driver_path import chrome_driver_path
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

class NjDmvScraper:
    def __init__(self, cities, search_months):
        self.cities = cities
        self.search_months = search_months
        self.base_url = 'https://telegov.njportal.com/njmvc/AppointmentWizard/7'
        self.driver = self._setup_chromedriver()
        phone_number = os.getenv("PHONE_NUMBER")
        self.phone_email = f"{phone_number}@vtext.com"
        self.found_appts = {}
        for city in cities:
            self.found_appts[city] = []

    def run(self):
        while True:
            try:
                self.check_open_appointments(quit_when_done=False)
                time.sleep(5)
            except Exception:
                self.driver.quit()

    def check_open_appointments(self, quit_when_done=True):
        for city in self.cities:
            self.driver.get(self.base_url)
            print (f'CHECKING APPOINTMENTS IN {city.title()}', flush=True)
            locations_div = self.driver.find_element_by_id(id_='locationsDiv')
            # I can get rid of the following for loop when I
            # figure out the correct xpath
            city_nodes = locations_div.find_elements_by_xpath(".//*")
            for city_node in city_nodes:
                city_regex = re.search(r".+,", city_node.text)
                if city_regex and "Next Available:" in city_node.text:
                    current_city = city_regex.group(0)[:-1].lower()
                    appt_dt = self.get_next_appt_dt(city_node.text)
                    if self._is_valid_appointment(city, current_city, appt_dt):
                        print (f'FOUND APPOINTMENT: {city.title()}', flush=True)
                        city_node.find_element_by_link_text("MAKE APPOINTMENT").click()
                        self.found_appts[city].append(appt_dt)
                        time.sleep(2)  # wait for page to load
                        self.send_message(current_city.title(),
                                        appt_dt.strftime("%m/%d/%Y %I:%M %p"),
                                        self.driver.current_url)
                        break
        if quit_when_done:
            self.driver.quit()

    def _is_valid_appointment(self, city1, city2, appt_dt):
        return (city1 == city2 and \
                appt_dt.strftime("%B") in self.search_months and \
                appt_dt not in self.found_appts[city1])

    def get_next_appt_dt(self, city_node_text):
        regex = r"(?<=Next Available:\s).+(?=\sMAKE APPOINTMENT)"
        dt_string = re.search(regex, city_node_text).group(0)
        return datetime.strptime(dt_string, "%m/%d/%Y %I:%M %p")

    def send_message(self, city_name, date, link):
        msg = MIMEMultipart()
        msg['From'] = os.environ.get('GMAIL')
        msg['To'] = self.phone_email
        msg['Subject'] = 'OPEN DMV APPOINTMENT'
        body = (f"Open appointmen in {city_name} on {date} \n {link}")
        msg.attach(MIMEText(body, 'html'))

        # creates SMTP session
        s = smtplib.SMTP('smtp.gmail.com', 587)

        # start TLS for security
        s.starttls()

        # Authentication
        s.login(os.environ.get('GMAIL'), os.environ.get('GMAIL_PASSWORD'))

        # Converts the Multipart msg into a string
        text = msg.as_string()

        # sending the mail
        s.sendmail(os.environ.get('GMAIL'), self.phone_email, text)

        # terminating the session
        s.quit()

    def _setup_chromedriver(self):
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        return webdriver.Chrome(chrome_driver_path, options=options)

cities = ['vineland', 'newark', 'wayne']
months = ['May', 'June', 'July']
NjDmvScraper(cities, months).run()
