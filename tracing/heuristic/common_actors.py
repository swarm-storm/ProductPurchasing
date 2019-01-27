import random
import sys
import traceback
import time
import csv
import sys
from selenium.common.exceptions import StaleElementReferenceException
from tracing.nlp import *
from tracing.common_heuristics import *
from selenium.webdriver.support.select import Select
from selenium.webdriver.common.keys import Keys
import tracing.selenium_utils.common as common
import tracing.selenium_utils.controls as controls
from tracing.heuristic.shop_tracer import *
from tracing.rl.actions import *
from tracing.rl.environment import *


class ToProductPageLink(IEnvActor):
    contains = ['/product', '/commodity', '/drug', 'details', 'view']
    not_contains = ['review', 'viewbox', 'view my shopping cart']

    def __init__(self):
        self.attempts = 3
        self.checked = {}

    def reset(self):
        self.attempts = 3

    def get_states(self):
        return [States.new, States.shop, States.found_product_in_cart]

    def get_action(self, control):
        if self.attempts <= 0 or control.type != controls.Types.link:
            return Nothing()

        link = control.elem.get_attribute('href')
        if link in self.checked:
            return Nothing()

        self.checked[link] = True

        text = control.elem.get_attribute('outerHTML')
        if nlp.check_text(text, self.contains, self.not_contains):
            self.attempts -= 1
            return Click()
        else:
            return Nothing()

    def get_state_after_action(self, is_success, state, control, environment):
        if not is_success:
            return (state, False)
        
        if AddToCart.find_to_cart_elements(environment.driver):
            qty_plus_icons = environment.driver.find_elements_by_class_name('edit-qty')
            if qty_plus_icons:
                for icon in qty_plus_icons:
                    if 'edit-qty plus' in icon.get_attribute('class'):
                        icon.click()
            return (States.product_page, False)
        
        # Discard last action
        return (state, True)

    
class AddToCart(IEnvActor):
    type_list = [
        controls.Types.link,
        controls.Types.button
    ]
    contains =  ["addtocart", "addtobag", "add to cart", "add to bag"]
    not_contains = ["where", "about us"]

    def __init__(self):
        self.attempts = 3

    def reset(self):
        self.attempts = 3

    def get_states(self):
        return [States.new, States.shop, States.product_page,
                States.found_product_page]

    @staticmethod
    def find_to_cart_elements(driver):
        return search_for_add_to_cart(driver)

    def get_action(self, control):

        if self.attempts <= 0 or control.type not in self.type_list:
            return Nothing()

        try:
            text = control.label
            if not text or not text.strip():
                text = control.elem.get_attribute('outerHTML')

            if nlp.check_text(text, self.contains, self.not_contains):
                if (control.elem.get_attribute('class') == 'button grouped-simple btn-cart') or (control.elem.get_attribute('outerHTML') == '<span>Add to Cart</span>'):
                    return Nothing()
                self.attempts -= 1
                return Click()
            else:
                return Nothing()
        except:
            return Nothing()

    def get_state_after_action(self, is_success, state, control, environment):
        if not is_success:
            return (state, False)

        new_state = States.found_product_in_cart if state == States.found_product_page else States.product_in_cart
        if not is_empty_cart(environment.driver):
            return (new_state, False)

        return (state, True)


class ToShopLink(IEnvActor):
    type_list = [
        controls.Types.link,
        controls.Types.button
    ]
    contains = ["shop", "store", "products"]
    not_contains = ["shops", "stores", "shopping", "condition", "policy"]

    def get_states(self):
        return [States.new, States.found_product_in_cart]

    def get_action(self, control):
        if control.type not in self.type_list:
            return Nothing()
        
        text = control.elem.get_attribute('outerHTML')
        if nlp.check_text(text, self.contains, self.not_contains):
            return Click()
        else:
            return Nothing()
    
    def get_state_after_action(self, is_success, state, control, environment):
        if not is_success:
            return (state, False)

        return (States.shop, False)


class ClosePopups(IEnvActor):
    type_list = [
        controls.Types.link,
        controls.Types.button,
        controls.Types.radiobutton,
        controls.Types.checkbox
    ]
    contains = ["i (. |)over", "i (. |)age", "i (.* |)year", "agree", "accept", "enter "]
    not_contains = ["not ", "under ", "leave", "login", "log in", "cancel", " none"]

    def get_states(self):
        return [States.new]

    def get_action(self, control):
        if control.type not in self.type_list:
            return Nothing()

        text = control.elem.get_attribute("innerHTML").strip() + \
               control.elem.text + " " + \
               (control.elem.get_attribute("value") if control.elem.get_attribute("value")  else "")

        if nlp.check_text(text, self.contains, self.not_contains):
            return Click()
        else:
            if control.type in [controls.Types.radiobutton, controls.Types.checkbox] and \
                nlp.check_text(controls.get_label(control.elem), self.contains, self.not_contains):
                return Click()
            return Nothing()
    
    def get_state_after_action(self, is_success, state, control, environment):
        return (state, False)

        
class ToCartLink(IEnvActor):
    type_list = [
        controls.Types.link,
    ]
    contains = ["cart"]
    not_contains = ["add", "append", "remove", "showcart"]

    def __init__(self):
        self.attempts = 3
        self.checked = {}

    def reset(self):
        self.attempts = 3

    def get_states(self):
        return [States.product_in_cart, States.found_product_in_cart]
    
    def get_action(self, control):
        if self.attempts <= 0 or control.type not in self.type_list:
            return Nothing()

        link = control.elem.get_attribute('href')
        if link in self.checked:
            if nlp.check_text(link, self.contains, self.not_contains):
                self.attempts -= 1
                return Click()
            return Nothing()

        self.checked[link] = True
        
        text = control.elem.get_attribute('outerHTML')
        if nlp.check_text(text, self.contains, self.not_contains):
            self.attempts -= 1
            return Click()
        else:
            return Nothing()

    def get_state_after_action(self, is_success, state, control, environment):
        if not is_success:
            environment.states.append(())
            return (state, False)

        time.sleep(3)

        is_empty = is_empty_cart(environment.driver)

        if is_empty:
            return (state, True)

        if not is_empty and ToCheckout.find_checkout_elements(environment.driver):
            return (States.cart_page, False)

        # Discard last action
        return (state, True)


class ToCheckout(IEnvActor):
    type_list = [
        controls.Types.link,
        controls.Types.button
    ]
    contains =  ["checkout", "check out"]
    not_contains = [
        'continue shopping', 'return',
        'guideline', 'login', 'log in',
        'sign in', 'view cart', 'logo',
    ]


    @staticmethod
    def find_checkout_elements(driver):
        btns = find_buttons_or_links(driver, ToCheckout.contains, ToCheckout.not_contains)

        # if there are buttons that contains words in text return them first
        exact = []
        for btn in btns:
            label = controls.get_label(btn)
            text = label or btn.get_attribute('outerHTML')
            if nlp.check_text(text.lower(), ToCheckout.contains, ToCheckout.not_contains):
                exact.append(btn)

        if len(exact) > 0:
            return exact

        return btns

    def get_states(self):
        return [States.product_in_cart,
                States.found_product_in_cart,
                States.cart_page,
                States.cart_page_2,
                States.cart_page_3
                ]

    def get_action(self, control):
        if control.type not in self.type_list:
            return Nothing()

        text = control.label or control.elem.get_attribute('outerHTML')

        if nlp.check_text(text, self.contains, self.not_contains):
            if (control.elem.tag_name == 'a') and ('/cart' in control.elem.get_attribute('href')):
                if '/checkout' not in control.elem.get_attribute('href'):
                    return Nothing()
            return Click()
        else:
            return Nothing()

    def get_next_cart_state(self, state):
        if not state.startswith(States.cart_page):
            return States.cart_page


        if state == States.cart_page:
            return States.cart_page_2
        elif state == States.cart_page_2:
            return States.cart_page_3
        else:
            return States.checkoutLoginPage


    def get_state_after_action(self, is_success, state, control, environment):
        if not is_success:
            return (state, False)
        
        time.sleep(3)
        close_alert_if_appeared(environment.driver)
        if ToCheckout.find_checkout_elements(environment.driver):
            new_state = self.get_next_cart_state(state)
            return (new_state, False)

        return (States.checkoutLoginPage, False)


class SearchForProductPage(ISiteActor):
    def get_states(self):
        return [States.new]

    def get_action(self, environment):
        return SearchProductPage()

    def get_state_after_action(self, is_success, state, environment):
        if not is_success:
            return state

        if AddToCart.find_to_cart_elements(environment.driver):
            qty_plus_icons = environment.driver.find_elements_by_class_name('edit-qty')
            if qty_plus_icons:
                for i in qty_plus_icons:
                    if 'edit-qty plus' in i.get_attribute('class'):
                        i.click()
            return States.found_product_page
        return state


class CheckoutLogin(IEnvActor):
    contains = ['continue', 'proceed', 'ahead', 'select shipping options']
    not_contains = [
        'login', 'signin', 'log-in', 'sign-in', 'register',
    ]

    def __init__(self):
        self.guest_found = False
        self.user_name_found = False
        self.password_found = False
        self.country_filled = False

    def __str__(self):
        return "CheckoutLogin"

    def get_states(self):
        return [States.checkoutLoginPage]

    def get_action(self, control):
        if control.type not in [controls.Types.link, controls.Types.button, controls.Types.radiobutton, controls.Types.text]:
            if control.type == controls.Types.select:
                if (Select(control.elem).first_selected_option.text == 'United States'):
                    return Nothing()
                if (control.values and 'Colorado' in control.values) or \
                        (control.label and ('state' in control.label.lower() or 'province' in control.label.lower())):
                    return Nothing()
                elif 'United States of America' in control.values:
                    self.country_filled = True
                    return InputSelectField('select-country-full')
                elif 'United States America' in control.values:
                    self.country_filled = True
                    return InputSelectField('select-country-full-short')
                elif 'United States' in control.values:
                    self.country_filled = True
                    return InputSelectField('select-country-short')
                elif 'USA' in control.values:
                    self.country_filled = True
                    return InputSelectField('select-country-short-form')
            return Nothing()

        text = control.elem.get_attribute('outerHTML')

        if nlp.check_text(text.lower(), ['email', 'username'], self.not_contains):
            self.user_name_found = True
        if nlp.check_text(text.lower(), ['password'], self.not_contains):
            self.password_found = True
        if (control.label and nlp.check_text(control.label.lower(), ['guest', 'skip login'], self.not_contains)) or (control.label and 'skip login' in control.label.lower()):
            self.guest_found = True
            return Click()
        elif self.guest_found and control.label and nlp.check_text(control.label, self.contains, self.not_contains):
            return Click()
        elif control.label and "place order" in control.label.lower():
            # return MarkAsSuccess()
            return Click()

        else:
            if control.label and nlp.check_text(control.label, self.contains, self.not_contains):
                if not self.guest_found:
                    if self.user_name_found and self.password_found:
                        return Nothing()
                    else:
                        return Click()

            return Nothing()

    def get_state_after_action(self, is_success, state, control, environment):

        if not is_success:
            return (state, False)
        try:
            if self.guest_found:
                return (States.fillCheckoutPage, False)

            if nlp.check_text(control.label, self.contains, self.not_contains) or \
            "place order" in control.label.lower():
                if self.guest_found:
                    return (States.fillCheckoutPage, False)
                if control.label.lower() == 'place order':
                    return (States.fillPaymentPage, False)
                if not environment.has_next_control():
                    # environment.refetch_controls()
                    return (States.fillCheckoutPage, False)
                else:
                    return (States.fillCheckoutPage, False)
            if not environment.has_next_control():
                return (States.fillCheckoutPage, False)
        except: pass

        return (state, False)


class FillingCheckoutPage(IEnvActor):
    type_list = [
        controls.Types.text, controls.Types.select, controls.Types.button, 
        controls.Types.link, controls.Types.radiobutton, controls.Types.checkbox
    ]
    contains = ['continue', 'payment', 'proceed', 'bill & ship', 'place order', 'select shipping options']
    not_contains = ['amazon', 'paypal', 'giftcode', 'machine', 'cards', 'gift']

    def __init__(self):
        self.state_control = None
        self.country_found = False
        self.has_google_auto_fill = False
        self.filled_country_state = False

    def __str__(self):
        return "FillingCheckoutPage"

    def get_states(self):
        return [States.fillCheckoutPage]

    def get_action(self, control):
        if control.type not in self.type_list:
            return Nothing()


        input_control_action = self.fill_user_inputs(control)

        if input_control_action:
            return input_control_action
        return Nothing()

    def get_state_after_action(self, is_success, state, control, environment):

        if not is_success:
            if control.label == 'Email or mobile phone number':
                control.elem.send_keys(environment.user_info.email)
            return (state, False)
        try:
            text = control.elem.get_attribute('outerHTML')
            if nlp.check_text(text.lower(), ['google autocomplete field'], ['mail', 'pin code', 'postal', 'phone']):
                suggestion_close = environment.driver.find_element_by_class_name('combo-box__header__button')
                suggestion_close.click()
            if self.country_found and self.state_control:
                environment.apply_action(self.state_control, InputSelectField('select-state-name'))
                self.state_control = None
                self.country_found = False
                self.filled_country_state = True

            if self.country_found and (control.label and nlp.check_text_with_label([text.lower(), control.label.lower()], ['state', 'province', 'division'], ['mail'])):
                self.filled_country_state = True

            if (control.type == controls.Types.text) and (control.elem.get_attribute('name') == 'phoneNumber1'):
                control.elem.clear()
                ph_no1 = environment.user_info.phone
                ph_no1 = ph_no1.replace('-', '')
                ph_no1 = ph_no1.replace('(', '')
                ph_no1 = ph_no1.replace(')', '')
                control.elem.send_keys(ph_no1[:3])

            if (control.type == controls.Types.text) and (control.elem.get_attribute('name') == 'phoneNumber2'):
                control.elem.clear()
                ph_no2 = environment.user_info.phone
                ph_no2 = ph_no2.replace('-', '')
                ph_no2 = ph_no2.replace('(', '')
                ph_no2 = ph_no2.replace(')', '')
                control.elem.send_keys(ph_no2[3:6])

            if (control.type == controls.Types.text) and (control.elem.get_attribute('name') == 'phoneNumber3'):
                control.elem.clear()
                control.elem.send_keys(environment.user_info.phone.split('-')[1])
                if self.state_control and not self.country_found:
                    if environment.driver.find_elements_by_class_name('usa'):
                        Select(self.state_control.elem).select_by_value(environment.user_info.state)

            if control.label and nlp.check_text(control.label.lower(), ['credit', 'checkout_braintree'], ['amazon', 'paypal']):
                return (States.fillPaymentPage, False)

            if control.label and nlp.check_text(control.label.lower(), self.contains, self.not_contains):
                if self.filled_country_state:
                    return (States.prePaymentFillingPage, False)
                if self.state_control and not self.country_found:
                    if environment.driver.find_elements_by_class_name('usa'):
                        environment.apply_action(self.state_control, InputSelectField('select-state-name'))
                        return (States.prePaymentFillingPage, False)
                if not self.country_found:
                    Select(environment.driver.find_element_by_class_name('country_to_state')).select_by_value("US")
                if not self.state_control:
                    Select(environment.driver.find_element_by_id('billing_state')).select_by_value(environment.context.user_info.state)
                if 'place order' in control.label.lower():
                    return (States.fillPaymentPage, False)                
                return (States.prePaymentFillingPage, False)
        except StaleElementReferenceException as e:
            if control.label=='Continue to shipping method':
                if self.country_found and self.state_control:
                    environment.apply_action(self.state_control, InputSelectField('select-state-name'))
                    self.state_control = None
                    self.country_found = False
                    self.filled_country_state = True
                return (States.prePaymentFillingPage, False)
            if control.label and control.label == 'Select Shipping Options':
                return (States.prePaymentFillingPage, False)
        except Exception as e:
            pass
        return (state, False)


class PrePaymentFillingPage(IEnvActor):
    type_list = [
        controls.Types.radiobutton,
        controls.Types.link,
        controls.Types.button,
        controls.Types.checkbox
    ]
    contains = ['continue', 'proceed', 'ahead']
    not_contains = [
        'login', 'signin', 'log-in', 'sign-in',
        'register','continue shopping', 'machine', 'cards'
    ]

    def __init__(self):
        self.card_text = ['credit card', 'credit-card', 'free']

    def __str__(self):
        return "PrePaymentFillingPage"

    def get_states(self):
        return [States.prePaymentFillingPage]

    def get_action(self, control):
        if control.type not in self.type_list:
            return Nothing()

        text = control.elem.get_attribute('outerHTML')

        if (nlp.check_text(text.lower(), self.card_text + self.contains, self.not_contains)) or \
            (control.label and nlp.check_text(control.label.lower(), self.card_text, self.not_contains)):
            return Click()

        else:
            return Nothing()

    def get_state_after_action(self, is_success, state, control, environment):
        if not is_success:
            return (state, False)
        try:
            text = control.elem.get_attribute('outerHTML')

            if nlp.check_text(text.lower(), self.contains, self.not_contains):
                return (States.fillPaymentPage, False)
        except StaleElementReferenceException as e:
            if control.label and control.label == 'SAVE & CONTINUE':
                return (States.fillPaymentPage, False)
            if nlp.check_text(control.label.lower(), ['payment method'], ['shipping']):
                return (States.fillPaymentPage, False)
        except:
            if nlp.check_text(control.label.lower(), ['payment method'], ['shipping']):
                return (States.fillPaymentPage, False)
            pass

        return (state, False)


class FillingPaymentPage(IEnvActor):
    type_list = [
        controls.Types.link, controls.Types.button,
        controls.Types.text, controls.Types.select, 
        controls.Types.radiobutton, controls.Types.checkbox
    ]
    contains = ['card type', 'credit-type', 'cctype', 'creditcardtype']
    not_contains = ['sign-in', 'continue shopping']

    def __init__(self):
        self.init_variables()

    def __str__(self):
        return "FillingPaymentPage"

    def get_filling_status(self):
        return self.card_number_filled and self.card_cvc_filled and self.card_month_filled and self.card_year_filled

    def init_variables(self):
        self.flag = True
        self.has_card_details = False
        self.card_number_filled = False
        self.card_cvc_filled = False
        self.card_month_filled = False
        self.card_year_filled = False
        self.place_order_control = None
        self.last_control = None

    def get_states(self):
        return [States.fillPaymentPage]

    def fill_creditcard_fields(self, get_cc_controls, environment):
        for cc_control in get_cc_controls:
            environment.driver.switch_to.frame(cc_control)
            number_element = environment.driver.find_element_by_xpath("//input[@name='number']")
            if 'visually-hidden' not in number_element.get_attribute("class"):
                number_element.send_keys(environment.payment_info.card_number)
            name_element = environment.driver.find_element_by_xpath("//input[@name='name']")
            if 'visually-hidden' not in name_element.get_attribute("class"):
                name_element.send_keys(environment.user_info.first_name)
            expiry_element = environment.driver.find_element_by_xpath("//input[@name='expiry']")
            if 'visually-hidden' not in expiry_element.get_attribute("class"):
                expiry_element.send_keys(environment.payment_info.expire_date_year)
            cvv_element = environment.driver.find_element_by_xpath("//input[@name='verification_value']")
            if 'visually-hidden' not in cvv_element.get_attribute("class"):
                cvv_element.send_keys(environment.payment_info.cvc)
            environment.driver.switch_to.default_content()
            time.sleep(3)

    def fill_payment_fields(self, environment):
        total_controls = environment.get_controls()
        for control in total_controls:
            if control.type == controls.Types.text:
                text = control.elem.get_attribute('outerHTML')
                card_number_text = [
                    'cc-number', 'cc_number', 'cc number', 'card number',
                    'card-number', 'card_number','ccno', 'creditcardnumber'
                ]
                if nlp.check_text(text.lower(), card_number_text, ['sign-in']):
                    self.card_number_filled = True
                    self.has_card_details = True
                    control.elem.clear()
                    control.elem.send_keys(environment.payment_info.card_number)
                elif (control.label and nlp.check_text(control.label.lower(), ['name on card', 'card-holder'], ['card-number'])) or \
                    nlp.check_text(text.lower(), ['name on card', 'holdersname', 'card-holder'], ['card-number']):
                    control.elem.clear()
                    control.elem.send_keys(environment.user_info.first_name)
                elif (control.label and nlp.check_text(control.label.lower(), ['verification', 'cvc', 'cvv', 'cccvd', 'csc'], ['card-number'])) or nlp.check_text(text.lower(), ['verification', 'cvc', 'cvv', 'cccvd', 'csc'], ['card-number']):
                    self.card_cvc_filled = True
                    control.elem.clear()
                    control.elem.send_keys(environment.payment_info.cvc)
                elif (control.label and ('mm' in control.label.lower() and 'yy' in control.label.lower())) or ('month' in text.lower() and 'year' in text.lower()) or ('mm' in text.lower() and 'yy' in text.lower()) or ('creditcardexp' in text.lower()):
                    self.card_month_filled = True
                    self.card_year_filled = True
                    control.elem.clear()
                    control.elem.send_keys(environment.payment_info.expire_date_year)
            if not self.card_number_filled:
                number_input = environment.driver.find_elements_by_xpath("//input[contains(@name,'CardNumber')]")
                if number_input:
                    self.card_number_filled = True
                    number_input[0].send_keys(environment.payment_info.card_number)
            if not self.card_cvc_filled:
                cvv_input = environment.driver.find_elements_by_xpath("//input[contains(@name,'VerificationNumber')]")
                if cvv_input:
                    self.card_cvc_filled = True
                    cvv_input[0].send_keys(environment.payment_info.cvc)

    def get_action(self, control):
        if control.type not in self.type_list:
            if self.place_order_control and self.get_filling_status():
                return Click()
            return Nothing()
        elif self.place_order_control and self.get_filling_status():
            return Click()


        control_result = self.fill_user_inputs(control)
        if control_result:
            if isinstance(control_result, Nothing):
                if self.last_control:
                    if control == self.last_control:
                        if control.label and (control.label == 'Proceed to Payment'):
                            return Click()
                        return MarkAsSuccess()
            else:
                return control_result

        text = control.elem.get_attribute('outerHTML')

        if control.type == controls.Types.text:

            card_number_text = [
                'cc-number', 'cc_number', 'cc number', 'card number',
                'card-number', 'card_number','ccno', 'creditcardnumber'
            ]
            if nlp.check_text(text.lower(), card_number_text, ['sign-in']):
                self.card_number_filled = True
                self.has_card_details = True
                return InputPaymentTextField('card-number')
            elif (control.label and nlp.check_text(control.label.lower(), ['name on card', 'card-holder'], ['card-number'])) or \
                nlp.check_text(text.lower(), ['name on card', 'holdersname', 'card-holder'], ['card-number']):
                return InputCheckoutFields("first_name")
            elif (control.label and nlp.check_text(control.label.lower(), ['verification', 'cvc', 'cvv', 'cccvd', 'csc'], ['card-number'])) or nlp.check_text(text.lower(), ['verification', 'cvc', 'cvv', 'cccvd', 'csc'], ['card-number']):
                self.card_cvc_filled = True
                return InputPaymentTextField('cvc')
            elif (control.label and ('mm' in control.label.lower() and 'yy' in control.label.lower())) or ('month' in text.lower() and 'year' in text.lower()) or ('mm' in text.lower() and 'yy' in text.lower()) or ('creditcardexp' in text.lower()):
                self.card_month_filled = True
                self.card_year_filled = True
                return InputPaymentTextField('input-card-month-year')
            elif 'month' in text:
                self.card_month_filled = True
                return InputPaymentTextField('input-card-month')
            elif 'year' in text:
                self.card_year_filled = True
                return InputPaymentTextField('input-card-year')
            elif nlp.check_text(text.lower(), ['post code', 'zip', 'postal', 'post-code', 'post_code'], ['card-number']):
                return InputCheckoutFields('zip')
            else:
                return Nothing()
        elif control.type == controls.Types.select:
            if nlp.check_text(text.lower(), self.contains, ['credit-card-number'])\
                    or control.label and nlp.check_text(control.label.lower(), self.contains, ['credit-card-number']):
                if 'Credit card' in control.values:
                    Select(control.elem).select_by_visible_text("Credit card")
                    return Nothing()
                else:
                    return InputSelectField('card-type')
            elif nlp.check_text(text.lower(), ['expiration', 'expire', 'year', 'month', 'ccexpm', 'ccexpy'], ['credit-card-number']):
                if nlp.check_text(text.lower(), ['month', 'mm', 'ccexpm'], ['year']):
                    self.card_month_filled = True
                    if '06 - June' in control.values:
                        return InputSelectField('expire-month-text-with-number-full')
                    elif '6 - June' in control.values:
                        return InputSelectField('expire-month-text-with-number-short')
                    elif 'June' in control.values:
                        return InputSelectField('expire-month-text-full')
                    elif 'Jun' in control.values:
                        return InputSelectField('expire-month-text-short')
                    elif '06' in control.values:
                        return InputSelectField('expire-month-number-full')
                    elif '6' in control.values:
                        return InputSelectField('expire-month-number-short')
                    else:
                        return InputSelectField('expire-month-text-full')
                elif nlp.check_text(text.lower(), ['year', 'yy', 'ccexpy'], ['month']):
                    self.card_year_filled = True
                    if '2021' in control.values:
                        return InputSelectField('expire-year-full')
                    elif '21' in control.values:
                        return InputSelectField('expire-year-short')
                    else:
                        return InputSelectField('expire-year-full')
                return Nothing()
            else:
                return Nothing()
        elif control.type == controls.Types.radiobutton:
            sub_contains = ['credit card', 'credit-card', 'free', 'liquid scentsations', 'braintree']
            sub_not_contains = ['number']

            if nlp.check_text(text.lower(), ['number'])\
                    or (control.label and nlp.check_text(control.label.lower(), sub_contains, sub_not_contains)):
                return Click()

            if 'different_billing_address_false' in text.lower():
                return Click()

            return Nothing()
        elif control.type in [controls.Types.button, controls.Types.link]:
            sub_contains = ['place order', 'continue', 'proceed', 'payment','pay for order', 'submit my order']
            sub_not_contains = ['sign-in', 'continue shopping', 'paypal', 'cheque', 'moneyorder', 'gift', 'machine', 'masterpass', 'label', 'and more', 'visa', 'mastercard', 'american express', 'discover', 'jcb']
            if (control.label and nlp.check_text(control.label.lower(), sub_contains, sub_not_contains)) or nlp.check_text(text.lower(), sub_contains, sub_not_contains):
                if 'giftcode' in text.lower():
                    return Nothing()
                if '<label' in text.lower():
                    return Nothing()
                if self.get_filling_status():
                    return Click()
                elif not self.has_card_details:
                    return Click()
                else:
                    self.place_order_control = control
                    return Nothing()
            if self.last_control:
                if control.label == 'Proceed to Payment':
                    return Click()
                if control == self.last_control:
                    return MarkAsSuccess()

            return Nothing()
        elif control.type == controls.Types.checkbox:

            if control.label and nlp.check_text(text.lower(), ['agreetermsandconditions', 'terms and conditions'], ['amazon', 'paypal']):
                return Click()
            else:
                return Nothing()
        else:
            return Nothing()

    def get_state_after_action(self, is_success, state, control, environment):

        if not is_success:
            return (state, False)
        try:

            if not self.last_control:
                total_controls = environment.controls

                for loop_control in total_controls:
                    self.last_control = loop_control

            if self.last_control:
                if control == self.last_control:
                    self.fill_payment_fields(environment)
                    if self.get_filling_status():
                        return (States.pay, False)
                        # return (States.purchased, False)
            if control.label and nlp.check_text(control.label.lower(), ['proceed to payment'], self.not_contains):
                time.sleep(5)
            if control.type in [controls.Types.text, controls.Types.select, controls.Types.radiobutton]:
                text = control.elem.get_attribute('outerHTML')
                if control.type == controls.Types.radiobutton:
                    if 'authorizenet' in control.label.lower():
                        old_c_idx = environment.c_idx
                        environment.refetch_controls()
                        environment.c_idx = old_c_idx
                if control.label and nlp.check_text(control.label.lower(), ['post code', 'zip', 'postal', 'post-code', 'post_code', 'postal code'], ['card-number']):
                    if self.get_filling_status():
                        return (States.pay, False)

                if control.type == controls.Types.select:
                    if nlp.check_text(text.lower(), ['year', 'yy', 'ccexpy'], ['month']):
                        if len(control.elem.find_elements_by_tag_name("option")[5].get_attribute('value')) == 4:
                            Select(control.elem).select_by_value('20' + environment.payment_info.expire_date_year)
                    if nlp.check_text(text.lower(), ['month', 'mm', 'ccexpm'], ['year']):
                        if control.elem.find_elements_by_tag_name("option")[5].get_attribute('value') == '5':
                            exp_month = environment.payment_info.expire_date_month
                            if exp_month[0] == '0':
                                exp_month = exp_month.replace('0', '')
                            Select(control.elem).select_by_value(exp_month)

                if (control.label and nlp.check_text(control.label.lower(), ['verification', 'cvc', 'cvv', 'cccvd'], ['card-number'])) or nlp.check_text(text.lower(), ['verification', 'cvc', 'cvv', 'cccvd'], ['card-number']):
                    if not environment.has_next_control():
                        environment.reset_control()
                else:
                    pass
            elif control.label and nlp.check_text(control.label.lower(), ['place order', 'pay for order', 'complete order'], self.not_contains):
                if self.get_filling_status():
                    return (States.purchased, False)
                else:
                    if not self.has_card_details:
                        get_cc_controls = environment.driver.find_elements_by_class_name('card-fields-iframe')
                        if len(get_cc_controls) > 1:
                            self.fill_creditcard_fields(get_cc_controls, environment)
                            return (States.purchased, False)
                        environment.refetch_controls()
            elif control.label and nlp.check_text(control.label.lower(), ['continue', 'order'], self.not_contains):
                text = control.elem.get_attribute('outerHTML')
                if 'credit card' in text.lower():
                    return (States.pay, False)
                if not self.get_filling_status():
                    if not self.has_card_details:
                        environment.refetch_controls()
                else:
                    if control.label and nlp.check_text(control.label.lower(), ['complete order'], self.not_contains):
                        return (States.purchased, False)
                    return (States.pay, False)
            elif self.get_filling_status():
                if environment.has_next_control():
                    next_ctrl = environment.get_next_control()
                    next_text = next_ctrl.elem.get_attribute('outerHTML')
                    if nlp.check_text(next_text.lower(), ['post code', 'zip', 'postal', 'post-code', 'post_code', 'postal code'], ['card-number']):
                        environment.apply_action(next_ctrl, InputPaymentTextField('cvc'))
                        return (States.pay, False)
                else:
                    self.flag = False
                    environment.reset_control()
            elif not self.get_filling_status():
                if not self.has_card_details:
                    environment.refetch_controls()
        except Exception as e:
            pass
        return (state, False)


class Pay(IEnvActor):
    type_list = [controls.Types.link, controls.Types.button]
    contains = ['continue', 'proceed', 'ahead', 'place', 'pay for order']
    not_contains = ['login', 'signin', 'log-in', 'sign-in', 'register', 'continue shopping', 'select2']

    def __str__(self):
        return "Pay"

    def get_states(self):
        return [States.pay]

    def get_action(self, control):

        if control.type not in self.type_list:
            return Nothing()
        text = control.elem.get_attribute('outerHTML')

        if nlp.check_text(text.lower(), self.contains, self.not_contains):
            return Click()

        else:
            return Nothing()

    def get_state_after_action(self, is_success, state, control, environment):
        if not is_success:
            return (state, False)

        try:
            if control.label and nlp.check_text(control.label.lower(), self.contains, self.not_contains):
                return (States.purchased, False)
            text = control.elem.get_attribute('outerHTML')

            if nlp.check_text(text.lower(), self.contains, self.not_contains):
                return (States.purchased, False)
        except:
            pass

        return (state, False)


def add_tracer_extensions(tracer):
    # tracer.add_handler(ClosePopups(), 5)

    tracer.add_handler(SearchForProductPage(), 4)
    tracer.add_handler(AddToCart(), 3)
    tracer.add_handler(ToProductPageLink(), 2)
    tracer.add_handler(ToShopLink(), 1)

    tracer.add_handler(ToCheckout(), 6)
    tracer.add_handler(ToCartLink(), 5)

    tracer.add_handler(CheckoutLogin(), 2)
    tracer.add_handler(FillingCheckoutPage(), 2)
    tracer.add_handler(PrePaymentFillingPage(), 2)
    tracer.add_handler(FillingPaymentPage(), 2)
    tracer.add_handler(Pay(), 2)
