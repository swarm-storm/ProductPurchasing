import random
import sys
import traceback
import time
import calendar
import csv
import sys

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import Select
from selenium.common.exceptions import ElementNotVisibleException, TimeoutException, StaleElementReferenceException, NoSuchElementException

sys.path.insert(0, '..')

from tracing.nlp import *
from tracing.shop_tracer import *
from tracing.selenium_utils.common import *
from tracing.selenium_utils.controls import *
from tracing.common_heuristics import *
from tracing.utils.logger import *


class ToProductPageLink(IStepActor):
    def get_states(self):
        return [States.new, States.shop]

    @staticmethod
    def find_to_product_links(driver):
        return find_links(driver, ['/product', '/commodity', '/drug', 'details', 'view'])

    @staticmethod
    def process_links(driver, state, links):
        if not links:
            return state

        attempts = 3
        links = list(links)
        random.shuffle(links)

        for i in range(attempts):
            if i >= len(links):
                break

            link = links[i]

            url = ShopTracer.normalize_url(link)
            driver.get(url)
            time.sleep(3)

            # Check that have add to cart buttons
            if AddToCart.find_to_cart_elements(driver):
                return States.product_page
            else:
                back(driver)

        return state

    def process_page(self, driver, state, context):
        links = list([link.get_attribute('href') for link in ToProductPageLink.find_to_product_links(driver)])
        return ToProductPageLink.process_links(driver, state, links)


class AddToCart(IStepActor):
    def get_states(self):
        return [States.new, States.shop, States.product_page]

    @staticmethod
    def find_to_cart_elements(driver):
        return find_buttons_or_links(driver, ["addtocart",
                                              "addtobag",
                                              "add to cart",
                                              "add to bag"], ['where'])

    def process_page(self, driver, state, context):
        elements = AddToCart.find_to_cart_elements(driver)

        if click_first(driver, elements, try_handle_popups, randomize = True):
            time.sleep(3)
            return States.product_in_cart
        else:
            return state


class ToShopLink(IStepActor):
    def get_states(self):
        return [States.new]

    def find_to_shop_elements(self, driver):
        return find_buttons_or_links(driver, ["shop", "store", "products"], ["shops", "stores", "shopping", "condition", "policy"])

    def process_page(self, driver, state, context):
        elements = self.find_to_shop_elements(driver)
        if click_first(driver, elements, try_handle_popups):
            return States.shop
        else:
            return state


class ClosePopups(IStepActor):
    def get_states(self):
        return [States.new]

    def process_page(self, driver, state, context):
        if try_handle_popups(driver):
            logger = get_logger()
            logger.info("Popup closed")

        return state


class ToCartLink(IStepActor):
    def find_to_cart_links(self, driver):
        return find_links(driver, ["cart"], ['add', 'append'])

    def get_states(self):
        return [States.product_in_cart]

    def process_page(self, driver, state, context):

        attempts = 3
        for attempt in range(attempts):
            btns = self.find_to_cart_links(driver)

            if len(btns) <= attempt:
                break

            if click_first(driver, btns, randomize = True):
                time.sleep(3)
                checkouts = ToCheckout.find_checkout_elements(driver)

                if not is_empty_cart(driver) and len(checkouts) > 0:
                    return States.cart_page
                else:
                    back(driver)


        return state


class ToCheckout(IStepActor):

    @staticmethod
    def find_checkout_elements(driver):
        contains =  ["checkout", "check out"]
        not_contains = ['continue shopping', 'return', 'guideline', 'login', 'log in', 'sign in', 'view cart', 'logo']
        btns = find_buttons_or_links(driver, contains, not_contains)

        # if there are buttongs that contains words in text return them first
        exact = []
        for btn in btns:
            text = btn.get_attribute('innerHTML')
            if nlp.check_text(text, contains, not_contains):
                exact.append(btn)

        if len(exact) > 0:
            return exact

        return btns

    def get_states(self):
        return [States.product_in_cart, States.cart_page]


    @staticmethod
    def has_checkout_btns(driver):
        btns = ToCheckout.find_checkout_elements(driver)
        return len(btns) > 0


    @staticmethod
    def process(driver, state, max_depth=3):
        btns = ToCheckout.find_checkout_elements(driver)

        if click_first(driver, btns):
            time.sleep(3)
            close_alert_if_appeared(driver)
            if not is_empty_cart(driver):
                if ToCheckout.has_checkout_btns(driver) and max_depth > 0:
                    ToCheckout.process(driver, state, max_depth - 1)

                return States.checkout_page

        return state

    def process_page(self, driver, state, context):
        return ToCheckout.process(driver, state)


class PaymentFields(IStepActor):
    def get_states(self):
        return [States.checkout_page]

    def check_login_exist(self, driver, context):
        '''
            Check login requiring in checkout page
        '''
        password_fields = driver.find_elements_by_css_selector("input[type='password']")
        logger = get_logger()

        if password_fields:
            if len(password_fields) >= 2:
                return True
            if password_fields[0].is_displayed():
                radio_or_check_continue = find_radio_or_checkbox_buttons(
                    driver,
                    ["guest", "create*.*later", "copy*.*ship",
                     "copy*.*bill", "skip*.*login", "register"]
                )
                if not radio_or_check_continue and \
                        not self.find_guest_continue_button(
                            driver,
                            ["continue", "checkout", "check out",
                             "(\s|^)go(\s|$)","new.*.customer"],
                            ["login", "continue shopping", "cart",
                             "logo", "return", "signin"]
                        ):
                    if not self.new_account_field_exist(driver,
                                                        ["guest", "(no|without|free|create).*account",
                                                         "account.*.(no|without|free)"],
                                                        ["login","signin","sign in"],
                                                        password_fields[0]):

                        logger.debug("We can't use this url! Login password required!")
                        return False
        return True

    def filter_page(self, driver, state, context):
        return_flag = True

        if not self.check_login_exist(driver, context):
            return_flag = False

        return return_flag

    def find_select_element(self, driver, contain, consider_contain=None):
        '''
            Find select elements containing content of contain parameter.
        '''
        selects = driver.find_elements_by_css_selector("select")
        selected_sels = []
        pass_once = False
        content = contain

        if consider_contain:
            if content == consider_contain[0]:
                content = consider_contain[1]
                pass_once = True

        for sel in selects:
            try:
                label_text = get_label_text_with_attribute(driver, sel)
            except:
                continue
            not_contains = []
            if content == "state":
                not_contains = ["unitedstate"]
            elif content == "ex":
                not_contains = ["state", "country", "express"]
            if nlp.check_text(label_text, [content], not_contains):
                if pass_once:
                    pass_once = False
                    continue
                selected_sels.append(sel)
        return selected_sels


    def find_guest_continue_button(self, driver, contains, not_contains):
        '''
            Find guest or continue button in case the password input field exist in checkout page
        '''
        pass_button = []

        text_element = find_text_element(
            driver,
            ["guest", "(no|without|free|create).*account",
             "account.*.(no|without|free)"])

        if text_element:
            for button in find_buttons_or_links(driver, contains, not_contains):
                if button.get_attribute("href") and \
                        button.get_attribute("href") in normalize_url(get_url(driver)):
                    continue
                pass_button.append(button)

            if not pass_button:
                pass_button = get_no_href_buttons(
                    driver,
                    ["forgot.*.password"],
                    ["cart", "logo", "return", "continue shopping"])

        return pass_button


    def new_account_field_exist(self, driver, contains, not_contains, create_new_field):
        text_element = find_text_element(driver, contains, not_contains)

        if text_element:
            root_element = text_element.find_element_by_xpath("../..")

            try:
                password_element = root_element.find_element_by_css_selector("input[type='password']")

                if password_element and password_element == create_new_field:
                    return True
            except:
                pass

        return False


    def process_select_option(self, driver, contains, context):
        '''
            Find select elements containing content of contains parameter
            and choose exact option with context
        '''
        result_cnt = 0

        for item in contains:
            selects = self.find_select_element(driver, item, ['ex1', 'ex'])
            if not selects:
                continue
            for sel in selects:
                try:
                    flag = False
                    for option in sel.find_elements_by_css_selector("option"):
                        text = option.text + " " + option.get_attribute("innerHTML").strip()
                        ctns  = []

                        if item == "country":
                            ctns = ["united states"]
                        elif item == "day":
                            ctns = ["27"]
                        elif item == "state":
                            ctns = [
                                nlp.normalize_text(get_name_of_state(context.user_info.state)),
                                "(^|\s){}$".format(nlp.normalize_text(context.user_info.state))
                            ]
                        else:
                            ctns = [
                                nlp.normalize_text(context.payment_info.card_type),
                                "(\d\d|^){}$".format(context.payment_info.expire_date_year),
                                "(^|-|_|\s|\d){}".format(nlp.normalize_text(calendar.month_abbr[int(context.payment_info.expire_date_month)])),
                                context.payment_info.expire_date_month
                            ]
                        if nlp.check_text(text, ctns):
                            try:
                                option.click() # select() in earlier versions of webdriver
                                time.sleep(context.delaying_time - 1)
                                result_cnt += 1
                                flag = True
                                break
                            except:
                                break
                    if flag:
                        break
                except:
                    continue
        return result_cnt


    def input_fields_in_checkout(self,
                                 driver,
                                 context,
                                 select_contains,
                                 extra_contains,
                                 is_userInfo=True,
                                 not_extra_contains=None,
                                 not_contains=None
                                 ):
        '''
            Choose select option and fill input fields.
            select_contains:
                find select options containing content of this parameter
            extra_contains:
                optimize attribute text by using content of this parameter
            is_userInfo:
                True: fill user information fields
                False: fill payment information field
        '''

        logger = get_logger()

        inputed_fields = []
        cycle_count = 0
        address_cnt = 0
        confirm_pwd = False
        index = 0

        selected_count = self.process_select_option(driver, select_contains, context)
        if not selected_count:
            logger.debug("Not found select options!")

        input_texts = driver.find_elements_by_css_selector("input")
        input_texts += driver.find_elements_by_css_selector("textarea")
        time.sleep(context.delaying_time - 1)

        if is_userInfo:
            json_Info = context.user_info.get_json_userinfo()
            confirm_pwd = False
        else:
            json_Info = context.payment_info.get_json_paymentinfo()
            confirm_pwd = True

        while index < len(input_texts):
            label_text = ""
            try:
                if input_texts[index].is_displayed() and \
                        not nlp.check_text(input_texts[index].get_attribute("type"),
                                           ["button", "submit", "radio", "checkbox", "image"]):
                    label_text = get_label_text_with_attribute(driver, input_texts[index])

                if not label_text:
                    index += 1
                    continue
            except:
                if cycle_count >= 2:
                    cycle_count = 0
                    index += 1
                    continue
                input_texts = driver.find_elements_by_css_selector("input")
                input_texts += driver.find_elements_by_css_selector("textarea")
                cycle_count += 1
                continue

            for conItem in extra_contains:
                not_text_contains = not_extra_contains
                if conItem[0] == "comp":
                    not_text_contains = not_text_contains + ["complete"]
                if nlp.check_text(label_text, conItem[0].split(","), not_text_contains):
                    if conItem[1] == "number" and nlp.check_text(label_text, ["verif.*"]):
                        conItem[1] = "cvc"
                    label_text += " " + conItem[1]
                    break
            for key in json_Info.keys():
                if key in inputed_fields:
                    continue
                _not_contains = not_contains
                if key == "type":
                    _not_contains = _not_contains + ["typehere"]
                elif key == "city":
                    _not_contains = _not_contains + ["opacity"]
                elif key == "number":
                    _not_contains = _not_contains + ["verif.*", "number\d"]
                if nlp.check_text(label_text.replace("name=", " ").replace("type=", " "), [nlp.remove_letters(key, [" "])], _not_contains):
                    try:
                        input_texts[index].click()
                        input_texts[index].clear()
                    except:
                        driver.execute_script("arguments[0].click();",input_texts[index])
                        input_texts[index].clear()
                        pass
                    try:
                        if key == "phone":
                            if nlp.check_text(input_texts[index].get_attribute("outerHTML"), ["email"]):
                                continue
                            input_texts[index].send_keys(nlp.remove_letters(json_Info[key], ["(", ")", "-"]))
                        elif key == "country":
                            input_texts[index].send_keys("united states")
                        elif key == "state":
                            input_texts[index].send_keys(nlp.normalize_text(get_name_of_state(context.user_info.state)))
                        elif key == "number":
                            input_texts[index].send_keys(json_Info[key])
                            input_texts[index].clear()
                            input_texts[index].send_keys(json_Info[key])
                            time.sleep(context.delaying_time + 1)
                        else:
                            input_texts[index].send_keys(json_Info[key])

                        if not is_userInfo and key == "zip":
                            time.sleep(context.delaying_time)
                        time.sleep(context.delaying_time - 1)
                    except:
                        break

                    inputed_fields.append(key)
                    if (key == "password" and not confirm_pwd) or (key == "email") or (key == "street"):
                        if key == "street":
                            if address_cnt >= 1:
                                break
                            address_cnt += 1
                        confirm_pwd = True
                        inputed_fields.pop()
                    break
            index += 1

        if len(inputed_fields) == 1 and inputed_fields[0] == "zip":
            return len(inputed_fields) - 1
        return len(inputed_fields)


    def check_error(self, driver, context):
        '''
            Check error elements after clicking continue(order) button
        '''
        logger = get_logger()
        error_result = []
        try:
            error_elements = find_error_elements(driver, ["error", "err", "alert", "advice", "fail", "invalid"], ["override"])
        except:
            if nlp.check_alert_text(driver, ["decline", "duplicate", "merchant", "transaction"]):
                return 2
            return 0
        time.sleep(context.delaying_time - 1)

        required_fields = driver.find_elements_by_css_selector("input")
        required_fields += driver.find_elements_by_css_selector("select")

        if error_elements:
            if len(error_elements) == 1 and nlp.check_text(
                    error_elements[0].get_attribute("outerHTML"),
                    ["credit", "merchant", "payment", "security","transaction", "decline", "permit", "authenticat"],
                    ["find", "require"]):
                return 2
            elif len(error_elements) == 2 and nlp.check_text(error_elements[1].get_attribute("outerHTML"), ["password"]):
                return 1

            if len(error_elements) <= 3:
                for error in error_elements:
                    if nlp.check_text(
                            error.get_attribute("outerHTML"),
                            ["already have an account with this email address",
                             "couldn't be verified",
                             "inactive for a while"]):
                        return 2

            while True:
                try:
                    for element in error_elements:
                        text = nlp.remove_letters(element.get_attribute("innerHTML").strip(), ["/", "*", "-", "_", ":", " "]).lower()
                        for field in required_fields:
                            if field.is_displayed():
                                label_text = get_label_text_with_attribute(driver, field)
                                if label_text and nlp.check_text(text, [label_text]):
                                    error_result.append(label_text + " field required")
                        if not error_result:
                            contain = ["password", "company", "first", "last", "address",
                                       "street", "city", "state", "zip", "phone",
                                       "email", "town", "cvc", "ccv", "credit"]
                            for item in contain:
                                not_contains = []
                                contains = [item]
                                if item == "address":
                                    not_contains = ["phone", "email"]
                                elif item == "state":
                                    contains.append("city")
                                    not_contains = ["\d+"]
                                elif item == "credit":
                                    contains.append("card")
                                if nlp.check_text(text, contains, not_contains):
                                    if item == "credit":
                                        item += " card"
                                    elif item == "first" or item == "last":
                                        item += " name"
                                    error_result.append(item + " field not correct or required")
                    break
                except:
                    error_elements = find_error_elements(driver, ["error", "err", "alert", "advice", "fail"], ["override"])
                    time.sleep(context.delaying_time - 1)
                    pass

            if not error_result:
                logger.debug("Input data not correct")
            for elem in error_result:
                if "password" in elem:
                    return 1
            return 0
        return 1

    def check_iframe_and_fill(self, driver, context):
        '''
            Find payment fieds in several iframes and fill them with payment information
        '''
        iframes = driver.find_elements_by_css_selector("iframe")
        enabled_iframes = []
        success_flag = False

        for iframe in iframes:
            if iframe.is_displayed():
                enabled_iframes.append(iframe)

        if not enabled_iframes:
            return False

        for iframe in enabled_iframes:
            driver.switch_to_frame(iframe)
            if self.fill_payment_info(driver, context):
                success_flag = True

            driver.switch_to_default_content()
            frames = driver.find_elements_by_css_selector("frame")
            if frames:
                driver.switch_to_frame(frames[0])
        return success_flag

    def click_continue_in_iframe(self, driver):
        '''
            find continue button in iframe and click
        '''
        iframes = driver.find_elements_by_css_selector("iframe")
        enabled_iframes = []
        success_flag = False

        for iframe in iframes:
            if iframe.is_displayed():
                enabled_iframes.append(iframe)

        if not enabled_iframes:
            return False

        for iframe in enabled_iframes:
            driver.switch_to_frame(iframe)
            self.check_agree_and_click(driver)
            elements = []

            for btn in find_buttons_or_links(driver, ["continu", "(\s|^)pay", "submit"]):
                if btn.get_attribute('href') == normalize_url(get_url(driver)):
                    continue
                elements.append(btn)
            if self.click_one_element(elements):
                success_flag = True
            driver.switch_to_default_content()

        return success_flag

    def check_agree_and_click(self, driver):
        '''
            Find radio and checkboxes for proceed and click
        '''
        agree_btns = find_radio_or_checkbox_buttons(
            driver,
            ["agree", "terms","same", "copy",
             "different", "register", "remember", "keep", "credit",
             "stripe", "mr", "standard", "free", "deliver",
             "billing_to_show", "ground", "idt", "gender"],
            ["express"]
        )
        cycle_count = 0
        index = 0

        if agree_btns:
            while index < len(agree_btns):
                try:
                    check_exception = agree_btns[index].get_attribute("outerHTML")
                except:
                    if cycle_count >= 2:
                        cycle_count = 0
                        index += 1
                        continue
                    agree_btns = find_radio_or_checkbox_buttons(
                        driver,
                        ["agree", "terms", "same", "copy",
                         "different", "remember", "keep", "credit", "stripe",
                         "register", "mr", "standard", "free", "deliver",
                         "billing_to_show", "ground", "idt", "gender"],
                        ["express"]
                    )
                    cycle_count += 1
                    continue

                if nlp.check_text(agree_btns[index].get_attribute("outerHTML"), ["diff", "register"]):
                    if not nlp.check_text(agree_btns[index].get_attribute("outerHTML"), ["radio", "same"]):
                        if agree_btns[index].is_displayed() and agree_btns[index].is_selected():
                            click_radio_or_checkout_button(driver, agree_btns[index])
                    elif nlp.check_text(agree_btns[index].get_attribute("outerHTML"), ["radio"]):
                        if nlp.check_text(agree_btns[index].get_attribute("outerHTML"), ["same"], ["to differ"]):
                            click_radio_or_checkout_button(driver, agree_btns[index])
                else:
                    if agree_btns[index].is_enabled() and not agree_btns[index].is_selected():
                        click_radio_or_checkout_button(driver, agree_btns[index])
                index += 1

        agree_btns = find_radio_or_checkbox_buttons(
            driver,
            ["paypal"],
            ["express", "differ", "register"]
        )
        cycle_count = 0
        index = 0

        if agree_btns:
            while index < len(agree_btns):
                try:
                    check_exception = agree_btns[index].get_attribute("outerHTML")
                except:
                    if cycle_count >= 2:
                        cycle_count = 0
                        index += 1
                        continue
                    agree_btns = find_radio_or_checkbox_buttons(
                        driver,
                        ["paypal"],
                        ["express", "differ", "register"]
                    )
                    cycle_count += 1
                    continue

                if agree_btns[index].is_enabled() and not agree_btns[index].is_selected():
                    click_radio_or_checkout_button(driver, agree_btns[index])
                index += 1

    def fill_billing_address(self, driver, context):
        '''
            Fill user fields with user information in checkout page
        '''
        select_contains = ["country", "state", "zone"]
        not_extra_contains = [
            "email", "firstname",
            "lastname", "street", "city",
            "company", "country", "state", "search"
        ]
        extra_contains = [
            ["(^|_|-|\s)fname,namefirst,username,first_name", "firstname"],
            ["(^|_|-|\s)lname,namelast,last_name", "lastname"],
            ["comp", "company"],
            ["post", "zip"],
            ["address,apartment,atp.", "street"]
        ]
        not_contains = [
            "phone(_|-|)(\w|\w\w|\w\w\w|)(2|3)"
        ]

        return self.input_fields_in_checkout(
            driver,
            context,
            select_contains,
            extra_contains,
            True,
            not_extra_contains,
            not_contains
        )

    def fill_payment_info(self, driver, context):
        '''
            Fill payment fields with payment information in checkout page
        '''
        select_contains = ["card", "month", "year", "day", "ex", "ex1"]
        not_extra_contains = ["company"]
        extra_contains = [
            ["owner", "name"],
            ["cc.*n,c\w+(num|num\w+),cardinput", "number"],
            ["comp", "company"],
            ["birth,(\w\w|\d\d)/(\w\w|\d\d)/(\w\w|\d\d|\d\d\d\d|\w\w\w\w)", "birthdate"],
            ["mm(|\w+)yy,(\w\w|\d\d)/(\w\w|\d\d)", "expdate"],
            ["exp", "expdate"],
            ["verif.*,sec.*,cv,cc(\w|)c,csc,card(\w+|\s|)code", "cvc"],
            ["post", "zip"]
        ]
        not_contains = [
            "first", "last", "phone", "company",
            "fname", "lname", "user", "email",
            "address", "street", "city",
            "gift", "vat", "filter"
        ]

        pay_result = self.input_fields_in_checkout(
            driver,
            context,
            select_contains,
            extra_contains,
            False,
            not_extra_contains = not_extra_contains,
            not_contains=not_contains
        )

        if pay_result == 3:
            return 0
        return pay_result

    def click_to_order(self, driver, context):
        '''
            Click pay or order button after filling user or payment fields.
        '''
        logger = get_logger()
        return_flag = True
        is_paymentinfo = False
        is_userinfo = False
        first_agree = False
        allow_fill_payment = True
        payment_url = None
        try_cnt = 0

        while True:
            if try_cnt >= 6:
                logger.debug("Error found in filling all fields")
                return_flag = False
                break

            if not first_agree:
                self.check_agree_and_click(driver)
                first_agree = True

            if not is_userinfo and self.fill_billing_address(driver, context):
                is_userinfo = True
                context.log_step("Fill user information fields")
                time.sleep(context.delaying_time - 1)

            div_btns = find_elements_with_attribute(driver, "div", "class", "shipping_method")

            if div_btns:
                div_btns[0].click()
                time.sleep(context.delaying_time - 1)

            if allow_fill_payment and not is_paymentinfo:
                if self.fill_payment_info(driver, context):
                    is_paymentinfo = True
                    context.log_step("Fill payment info fields")
                else:
                    if self.check_iframe_and_fill(driver, context):
                        is_paymentinfo = True
                        context.log_step("Fill payment info fields")

            order = get_no_href_buttons(
                driver,
                ["order", "pay", "checkout", "payment", "buy"],
                ["add", "modify", "coupon", "express",
                 "continu", "border", "proceed", "review",
                 "guest", "complete", "detail", "\.paypal\.",
                 "currency", "histor", "amazon", "summary toggle"], 2
            )

            if order:
                break

            continue_btns = get_no_href_buttons(driver,
                                                ["continu", "next", "proceed", "complete"],
                                                ["login", "cancel"]
                                                )
            flag = False

            if continue_btns:
                try:
                    continue_btns[len(continue_btns) - 1].click()
                except:
                    flag = True
                    pass
            if flag or not continue_btns:
                continue_btns = get_no_href_buttons(
                    driver,
                    ["bill", "proceed", "(\s|^)pay", "submit", "create*.*account",
                     "add", "save", "select shipping option"],
                    ["modify", "express", "cancel", "login", "sign in"]
                )

                if not continue_btns:
                    if is_userinfo or is_paymentinfo:
                        logging.debug("Proceed button not found!")
                    return_flag = False
                    break
                try:
                    continue_btns[len(continue_btns) - 1].click()
                except:
                    driver.execute_script("arguments[0].click();",continue_btns[len(continue_btns) - 1])
                    pass
            time.sleep(context.delaying_time * 3)
            checked_error = self.check_error(driver, context)

            if not checked_error:
                logging.debug("Error found in checking!")
                return_flag = False
                break
            elif checked_error == 1:
                if nlp.check_alert_text(driver, ["decline", "duplicate", "merchant", "transaction"]):
                    return True
                purchase_text = get_page_text(driver)
                if nlp.check_text(purchase_text, ["being process", "logging"]):
                    time.sleep(context.delaying_time - 1)
                elif nlp.check_text(purchase_text, ["credit card to complete your purchase", "secure payment page"]):
                    return True
            elif checked_error == 2:
                return True

            allow_fill_payment = False
            self.check_agree_and_click(driver)
            allow_number = check_filling_fields_required(driver)

            if allow_number == 1:
                is_userinfo = False
            elif allow_number == 2:
                allow_fill_payment = True
            elif allow_number == 3:
                is_userinfo = False
                allow_fill_payment = True

            if allow_number != 3 and allow_number != 2:
                page_text = get_page_text(driver)

                if nlp.check_text(page_text.lower(), ["cardholder", "card number", "expire"]):
                    allow_fill_payment = True
            try_cnt += 1

        if not return_flag:
            return False

        if order[0].get_attribute("href") and not "java" in order[0].get_attribute("href"):
            payment_url = order[0].get_attribute("href")

        #paying or clicking place order
        try:
            order[0].click()
        except:
            driver.execute_script("arguments[0].click();", order[0])
            pass

        time.sleep(context.delaying_time * 2)

        if nlp.check_alert_text(driver, ["decline", "duplicate", "merchant", "transaction"]):
            return True

        checked_error = self.check_error(driver, context)

        if not checked_error:
            return False
        elif checked_error == 2:
            return True

        #paying if payment info is not inputed
        if payment_url:
            driver.get(payment_url)

        if not is_paymentinfo:
            for _ in range(0, 3):
                pay_buttons = []
                if not self.fill_payment_info(driver, context) \
                        and not self.check_iframe_and_fill(driver, context):
                    logging.debug("Payment information is already inputed or payment field not exist!")
                else:
                    is_paymentinfo = True
                    context.log_step("Fill payment info fields")

                if return_flag:
                    pay_buttons = get_no_href_buttons(driver, ["pay", "order", "submit"], ["border"], 2)
                if pay_buttons:
                    self.check_agree_and_click(driver)
                    if not simply_click_one_element(pay_buttons):
                        if self.click_continue_in_iframe(driver):
                            return_flag = True
                            continue
                        logging.debug("Pay or order button error!")
                        return_flag = False
                    else:
                        if not self.click_continue_in_iframe(driver):
                            return_flag = False
                        else:
                            return_flag = True

                        time.sleep(context.delaying_time - 1)
                else:
                    return_flag = False

        checked_error = self.check_error(driver, context)

        if return_flag or checked_error == 2:
            return_flag = True
        elif not return_flag and checked_error == 1:
            blog_text = get_page_text(driver)
            if nlp.check_text(blog_text, ["thank(s|)\s.*purchase"]):
                return_flag = True
        return return_flag


    def process_page(self, driver, state, context):
        radio_pass = find_radio_or_checkbox_buttons(
            driver,
            ["guest", "create*.*later", "copy*.*ship",
             "copy*.*bill", "skip*.*login", "register"]
        )

        if radio_pass:
            #click an radio as guest....
            if not click_first(driver, radio_pass):
                return state
            time.sleep(context.delaying_time - 1)

        continue_pass = self.find_guest_continue_button(
            driver,
            ["continue", "checkout", "check out",
             "(\s|^)go(\s|$)","new.*.customer"],
            ["login", "continue shopping", "cart",
             "logo", "return", "signin"]
        )

        if continue_pass:
            #Fill email field if exist...
            guest_email = []

            for email in driver.find_elements_by_css_selector("input[type='email']"):
                if can_click(email):
                    guest_email.append(email)

            if guest_email:
                for g_email in guest_email:
                    g_email.send_keys(context.user_info.email)
                time.sleep(context.delaying_time - 1)
            #click continue button for guest....
            try:
                continue_pass[0].click()
            except:
                driver.execute_script("arguments[0].click();", continue_pass[0])
                pass
            time.sleep(context.delaying_time - 1)

        #the case if authentication is not requiring....
        filling_result = self.click_to_order(driver, context)
        if not filling_result:
            return state

        return States.purchased


class SearchForProductPage(IStepActor):

    def get_states(self):
        return [States.new, States.shop]

    def search_in_google(self, driver, query):
        driver.get('https://www.google.com')
        time.sleep(3)

        search_input = driver.find_element_by_css_selector('input.gsfi')
        search_input.clear()
        search_input.send_keys(query)
        search_input.send_keys(Keys.ENTER)
        time.sleep(3)

        links = driver.find_elements_by_css_selector('div.g .rc .r a[href]')
        if len(links) > 0:
            return [link.get_attribute("href") for link in links]
        else:
            return None

    def search_in_bing(self, driver, query):
        driver.get('https://www.bing.com')
        time.sleep(3)

        search_input = driver.find_element_by_css_selector('input.b_searchbox')
        search_input.clear()
        search_input.send_keys(query)
        search_input.send_keys(Keys.ENTER)
        time.sleep(3)

        links = driver.find_elements_by_css_selector('ol#b_results > li.b_algo > h2 > a[href]')

        if len(links) > 0:
            return [link.get_attribute("href") for link in links]
        else:
            return None

    def search_for_product_link(self, driver, domain):
        queries = ['"add to cart"']

        links = None
        # Open a new tab
        try:
            new_tab(driver)
            for query in queries:
                google_query = 'site:{} {}'.format(domain, query)

                searches = [self.search_in_bing, self.search_in_google]
                for search in searches:
                    try:
                        links = search(driver, google_query)
                        if links:
                            return links

                    except:
                        logger = get_logger()
                        logger.exception('during search in search engine got an exception')

        finally:
            # Close new tab
            close_tab(driver)

        return links

    def process_page(self, driver, state, context):
        links = self.search_for_product_link(driver, context.domain)

        if links:
            return ToProductPageLink.process_links(driver, state, links)

        return state


def add_tracer_extensions(tracer):
    tracer.add_handler(ClosePopups(), 5)

    tracer.add_handler(AddToCart(), 4)
    tracer.add_handler(SearchForProductPage(), 1)
    tracer.add_handler(ToProductPageLink(), 3)
    tracer.add_handler(ToShopLink(), 2)

    tracer.add_handler(ToCheckout(), 3)
    tracer.add_handler(ToCartLink(), 2)
    tracer.add_handler(PaymentFields(), 2)