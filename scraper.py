import time
import re
import os
import smtplib

from datetime import datetime
from selenium import webdriver
from drivers.driver_path import chrome_driver_path
from twilio.rest import Client
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

class NjDmvScraper:
    '''
    This class scapes the NJ dmv appointment website for OUT OF STATE
    LICENSE TRANSERS ONLY. To check for other appointments change self.base_url

    Parameters:
        cities: list of cities to check appointents for. (ex:['newark', 'wayne'] )
        serach_month: list of months to check for open appointments. (ex:['May', 'June'] )

    Environment Variables:
        PHONE_NUMBER: a valid verizon wireless phone number to send texts to.
            must be version because verizon "vtext" functionality is used.
        GMAIL: gmail.com email address
        GMAIL_PASSWORD: password for gmail email address

    '''
    def __init__(self, cities:list[str], search_months:list[str]):
        self.cities = cities
        self.search_months = search_months
        self.base_url = 'https://telegov.njportal.com/njmvc/AppointmentWizard/7'
        self.driver = self._setup_chromedriver()
        self.phone_number = os.getenv("PHONE_NUMBER")
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        self.twilio_client = Client(account_sid, auth_token)
        if not self.phone_number or not account_sid or not auth_token:
            raise Exception('Ensure the following env vars are defined PHONE_NUMBER, TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN')
        self.phone_email = f"{self.phone_number}@vtext.com"
        self.found_appts = {}
        for city in cities:
            self.found_appts[city] = []

    def run(self):
        '''
        Check DMV appointments every minute until the program is killed
        '''
        while True:
            try:
                self.check_open_appointments(quit_when_done=False)
                time.sleep(30)
            except Exception:
                self.driver.quit()

    def check_open_appointments(self, quit_when_done:bool=True):
        '''
        Checks base url for open appointments within the given cities and months
        that were given in the constructor.

        Parameters:
            quit_when_done: close chrome driver when execution is finished

        '''
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

    def _is_valid_appointment(self, city1: str, city2: str, appt_dt: datetime):
        '''
        Helper function to determine if the cities match, the appointment
        date is in the search_months and if we have already found the appointment

        Parameters:
            city1: a city name.
            city2: a city name.
            appt_dt: appointment datetime object

        Return: bool

        '''
        return (city1 == city2 and \
                appt_dt.strftime("%B") in self.search_months and \
                appt_dt not in self.found_appts[city1])

    def get_next_appt_dt(self, city_node_text:str):
        '''
        Parse out date from city node text using %m/%d/%Y %I:%M %p"
        pattern and convert it to a datetie object

        Parameters:
            city_node_text: text from the city node html

        Return: datetime

        '''
        regex = r"(?<=Next Available:\s).+(?=\sMAKE APPOINTMENT)"
        dt_string = re.search(regex, city_node_text).group(0)
        return datetime.strptime(dt_string, "%m/%d/%Y %I:%M %p")

    def send_message(self, city_name:str, date:str, link:str):
        '''
        Sends a text message to the verizon phone number given
        in the environment variable PHONE_NUMBER by sending an
        email from the gmail account specified using the
        environment varibles GMAIL and GMAil_PASSWORD.

        Note: you can only send emails to a phone number if its a
        verizon phone number.

         Parameters:
            city_name: city name of the appointment.
            date: date of the appointment.
            link: link to the appointment.
        '''
        body = (f"Open appointment in {city_name} on {date} \n {link}")
        self.twilio_client.messages \
                .create(
                     body=body,
                     from_='+15184788066',
                     to='+1' + self.phone_number
                )

        msg = MIMEMultipart()
        msg['From'] = os.environ.get('GMAIL')
        msg['To'] = self.phone_email
        msg['Subject'] = 'OPEN DMV APPOINTMENT'
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
        '''
        Setup and init chrome driver.
        '''
        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        return webdriver.Chrome(chrome_driver_path, options=options)

if __name__ == "__main__":
    cities = ['wayne']
    months = ['June', 'July']
    scraper = NjDmvScraper(cities, months)
    scraper.run()
