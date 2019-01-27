import requests
import selenium
from abc import abstractmethod
from tracing.common_heuristics import *
from tracing.status import *
from tracing.rl.environment import Environment
import tracing.selenium_utils.controls as controls
from tracing.rl.actions import *
from selenium.webdriver.support.select import Select
from tracing.utils.logger import *


class ITraceListener:

    def on_tracing_started(self, url):
        pass

    def on_handler_started(self, environment, handler, state):
        pass

    def before_action(self, environment, control = None, state = None, handler = None, frame_idx = None):
        pass

    def after_action(self, action, is_success, new_state = None):
        pass

    def on_tracing_finished(self, status):
        pass


class States:
    new = "new"
    shop = "shop"
    product_page = "product_page"
    found_product_page = "found_product_page"
    found_product_in_cart = "found_product_in_cart"
    product_in_cart = "product_in_cart"
    cart_page = "cart_page"
    cart_page_2 = "cart_page_2"
    cart_page_3 = "cart_page_3"
    checkout_page = "checkout_page"
    payment_page = "payment_page"
    purchased = "purchased"
    checkoutLoginPage = "checkout_login_page"
    prePaymentFillingPage = "pre_payment_filling_page"
    fillCheckoutPage = "fill_checkout_page"
    prePaymentFillingPage = "pre_payment_filling_page"
    fillPaymentPage = "fill_payment_page"
    pay = "pay"

    states = [
        new, shop, product_page, found_product_page,
        product_in_cart, found_product_in_cart,
        cart_page, cart_page_2, cart_page_3,
        checkout_page, checkoutLoginPage, fillCheckoutPage,
        prePaymentFillingPage, fillPaymentPage, pay, purchased
    ]


class TraceContext:
    def __init__(self, domain, delaying_time, tracer):
        self.domain = domain
        self.tracer = tracer
        self.trace_logger = tracer._trace_logger
        self.trace = None
        self.state = None
        self.url = None
        self.delaying_time = delaying_time
        self.is_started = False

    @property
    def driver(self):
        return self.tracer.environment.driver

    def on_started(self):
        assert not self.is_started, "Can't call on_started when is_started = True"
        self.is_started = True
        self.state = States.new
        self.url = get_url(self.driver)
    
        if self.trace_logger:
            self.trace = self.trace_logger.start_new(self.domain)
            self.log_step(None, 'started')
    
    def on_handler_finished(self, state, handler):
        if self.state != state or self.url != get_url(self.driver):
            self.state = state
            self.url = get_url(self.driver)
            self.log_step(str(handler))
    
    def on_finished(self, status):
        assert self.is_started, "Can't call on_finished when is_started = False"
        self.is_started = False
        
        if not self.trace_logger:
            return
        
        self.log_step(None, 'finished')
        
        self.trace_logger.save(self.trace, status)
        self.trace = None
    
    def log_step(self, handler, additional = None):
        if not self.trace:
            return


class IEnvActor:

    @abstractmethod
    def __init__(self):
        pass

    @abstractmethod
    def get_states(self):
        """
        States for actor
        """
        raise NotImplementedError

    @abstractmethod
    def reset(self):
        pass

    @abstractmethod
    def filter_page(self, driver, state, context):
        return True

    @abstractmethod
    def get_action(self, control):
        """
        Should return an action for every control
        """
        raise NotImplementedError

    @abstractmethod
    def get_state_after_action(self, is_success, state, control, environment):
        """
        Should return a new state or the old state
        Also should return wheather environmenet should discard last action
        """
        raise NotImplementedError

    def fill_user_inputs(self, control):
        if control.type == controls.Types.text:
            if control.elem.get_attribute('value'):
                if (control.label) and (control.elem.get_attribute('value') == control.label):
                    pass
                else:
                    return Nothing()
            if not control.label:
                text = control.elem.get_attribute('outerHTML')

            text = control.elem.get_attribute('outerHTML')
            if (control.label and nlp.check_text_with_label([text.lower(), control.label.lower()], ['first-name', 'first_name', 'first name', 'firstname', 'f_name', 'f-name', 'fname'], ['last_name'])) or nlp.check_text(text.lower(), ['first-name', 'first_name', 'first name', 'firstname', 'f_name', 'f-name', 'fname'], ['last_name']):
                return InputCheckoutFields("first_name")
            elif (control.label and nlp.check_text_with_label([text.lower(), control.label.lower()], ['last-name', 'last_name', 'last name', 'lastname', 'l_name', 'l-name', 'lname'], ['first_name'])) or nlp.check_text(text.lower(), ['last-name', 'last_name', 'last name', 'lastname', 'l_name', 'l-name', 'lname'], ['first_name']):
                return InputCheckoutFields("last_name")
            elif (control.label and nlp.check_text_with_label([text.lower(), control.label.lower()], ['email', 'e-mail', 'e_mail'], ['first_name', 'email_or_phone'])) or nlp.check_text(text.lower(), ['email', 'e-mail', 'e_mail'], ['first_name', 'email_or_phone']):
                return InputEmail()
            elif (control.label and nlp.check_text_with_label([text.lower(), control.label.lower()], ['street', 'road', 'address', 'apartment'], ['mail', 'pin code', 'postal', 'phone'])) or nlp.check_text(text.lower(), ['street', 'road', 'address', 'apartment'], ['mail', 'pin code', 'postal', 'phone']):
                return InputCheckoutFields("street")
            elif ('country' in text) and ('phone' not in text) :
                return InputCheckoutFields("country")
            elif (control.label and nlp.check_text_with_label([text.lower(), control.label.lower()], ['town', 'city'], ['mail'])) or nlp.check_text(text.lower(), ['town', 'city'], ['mail']):
                return InputCheckoutFields("city")
            elif (control.label and nlp.check_text_with_label([text.lower(), control.label.lower()], ['state', 'province', 'division'], ['mail'])) or nlp.check_text(text.lower(), ['state', 'province', 'division'], ['mail']):
                return InputCheckoutFields("state")
            elif (control.label and nlp.check_text_with_label([text.lower(), control.label.lower()], ['phone', 'mobile', 'telephone'])) or nlp.check_text(text.lower(), ['phone', 'mobile', 'telephone']):
                if control.elem.get_attribute('name') in ["phoneNumber1", 'phoneNumber2', 'phoneNumber3']:
                    return MarkAsSuccess()
                return InputCheckoutFields("phone")
            elif (control.label and nlp.check_text_with_label([text.lower(), control.label.lower()], ['post', 'zip'], ['submit'])) or nlp.check_text(text.lower(), ['post', 'zip'], ['submit']):
                return InputCheckoutFields("zip")
            else:
                return Nothing()
        elif control.type == controls.Types.select:
            if (control.values and 'Colorado' in control.values) or \
                    (control.label and nlp.check_text(control.label.lower(), ['state', 'province'], ['country', 'united states'])):

                self.state_control = control
                return Nothing()
            if (Select(control.elem).first_selected_option.text == 'United States'):
                self.country_found = True
            elif 'United States of America' in control.values:
                self.country_found = True
                return InputSelectField('select-country-full')
            elif 'United States America' in control.values:
                self.country_found = True
                return InputSelectField('select-country-full-short')
            elif 'United States' in control.values:
                self.country_found = True
                return InputSelectField('select-country-short')
            elif 'USA' in control.values:
                self.country_found = True
                return InputSelectField('select-country-short-form')
            return Nothing()
        elif control.type == controls.Types.radiobutton:
            if control.label and nlp.check_text(control.label.lower(), ['credit', 'checkout_braintree'], ['amazon', 'paypal']):
                return Click()
            else:
                return Nothing()
        elif control.type == controls.Types.checkbox:
            text = control.elem.get_attribute('outerHTML')
            if 'setAsBillingAddress' in text:
                return Click()
            else:
                return Nothing()
        elif control.type in [controls.Types.link, controls.Types.button]:
            text = control.elem.get_attribute('outerHTML')
            if (control.label and nlp.check_text(control.label.lower(), self.contains, self.not_contains)):
                if 'giftcode' in text.lower():
                    return Nothing()
                return Click()
            if (control.label and nlp.check_text(control.label.lower(), ['credit'], ['amazon', 'paypal', 'machine', 'cards', 'gift'])):
                return Click()
            return Nothing()
        else:
            return Nothing()


    def can_handle(self, driver, state, context):
        states = self.get_states()

        if states and state not in states:
            return False

        return self.filter_page(driver, state, context)


class ISiteActor:

    @abstractmethod
    def __init__(self):
        pass

    @abstractmethod
    def reset(self):
        pass

    @abstractmethod
    def get_states(self):
        """
        States for actor
        """
        raise NotImplementedError

    @abstractmethod
    def filter_page(self, driver, state, context):
        return True

    @abstractmethod
    def get_action(self, environment):
        """
        Should return an action for whole site
        """
        raise NotImplementedError

    @abstractmethod
    def get_state_after_action(self, is_success, state, environment):
        """
        Should return a new state or the old state
        Also should return wheather environmenet should discard last action
        """
        raise NotImplementedError
    
    def can_handle(self, driver, state, context):
        states = self.get_states()

        if states and state not in states:
            return False

        return self.filter_page(driver, state, context)


class ShopTracer:
    def __init__(self,
                 environment,
                 chrome_path='/usr/bin/chromedriver',
                 # Must be an instance of ITraceSaver
                 trace_logger = None
                 ):
        """
        :param environment    Environment that wraps selenium

        :param chrome_path:   Path to chrome driver
        :param headless:      Wheather to start driver in headless mode
        :param trace_logger:  ITraceLogger instance that could store snapshots and source code during tracing
        """
        if environment is None:
            environment = Environment()

        self.environment = environment
        self._handlers = []
        self._chrome_path = chrome_path
        self._logger = get_logger()
        self._headless = environment.headless
        self._trace_logger = trace_logger

        self.action_listeners = []

    def __enter__(self):
        pass
    
    def __exit__(self, type, value, traceback):
        self.environment.__exit__(type, value, traceback)

    def add_listener(self, listener):
        self.action_listeners.append(listener)

    def on_tracing_started(self, url):
        for listener in self.action_listeners:
            listener.on_tracing_started(url)

    def on_handler_started(self, environment, handler, state):
        for listener in self.action_listeners:
            listener.on_handler_started(environment, handler, state)

    def on_before_action(self, control = None, state = None, handler = None):
        for listener in self.action_listeners:
            listener.before_action(self.environment, control, state, handler, self.environment.f_idx)

    def on_after_action(self, action, is_success, new_state = None):
        for listener in self.action_listeners:
            listener.after_action(action, is_success, new_state)

    def on_tracing_finished(self, status):
        for listener in self.action_listeners:
            listener.on_tracing_finished(status)

    def add_handler(self, actor, priority=1):
        assert priority >= 1 and priority <= 10, \
            "Priority should be between 1 and 10 while got {}".format(priority)
        self._handlers.append((priority, actor))

    @staticmethod
    def normalize_url(url):
        if url.startswith('http://') or url.startswith('https://'):
            return url
        return 'http://' + url
    
    @staticmethod
    def get(driver, url, timeout=10):
        try:
            driver.get(url)
            response = requests.get(url, verify=False, timeout=timeout)
            code = response.status_code
            if code >= 400:
                return RequestError(code)
            
            return None
        
        except selenium.common.exceptions.TimeoutException:
            return Timeout(timeout)
            
        except requests.exceptions.ConnectionError:
            return NotAvailable(url)

    def apply_actor(self, actor, state):
        self.on_handler_started(self.environment, actor, state)

        if isinstance(actor, ISiteActor):
            self.on_before_action(state=state, handler=actor)

            action = actor.get_action(self.environment)
            self.environment.save_state()

            is_success,_ = self.environment.apply_action(None, action)
            new_state = actor.get_state_after_action(is_success, state, self.environment)

            if new_state != state:
                self.on_after_action(action, True, new_state = new_state)
                return new_state
            else:
                self.on_after_action(action, False, new_state = new_state)
                self.environment.discard()
        else:
            assert isinstance(actor, IEnvActor), "Actor {} must be IEnvActor".format(actor)

            while self.environment.has_next_control():
                ctrl = self.environment.get_next_control()
                self.on_before_action(ctrl, state = state, handler=actor)
                action = actor.get_action(ctrl)
                if not isinstance(action, Nothing):
                    self.environment.save_state()

                is_success,_ = self.environment.apply_action(ctrl, action)
                is_success = is_success and not isinstance(action, Nothing)
                new_state, discard = actor.get_state_after_action(is_success, state, ctrl, self.environment)
                self.on_after_action(action, is_success and not discard, new_state=new_state)

                if not isinstance(action, Nothing):
                    self._logger.info('is_success: {}, discard: {}'.format(is_success, discard))

                # Discard last action
                if discard:
                    self.environment.discard()
                    
                if new_state != state:
                    return new_state        
        return state

    def process_state(self, state, context):
        # Close popups if appeared
        close_alert_if_appeared(self.environment.driver)

        handlers = [(priority, handler) for priority, handler in self._handlers
                    if handler.can_handle(self.environment.driver, state, context)]

        handlers.sort(key=lambda p: -p[0])

        self._logger.info('processing state: {}'.format(state))
        for priority, handler in handlers:
            handler.reset()
            self.environment.reset_control()
            self._logger.info('handler {}'.format(handler))
            new_state = self.apply_actor(handler, state)

            self._logger.info('new_state {}, url {}'.format(new_state, get_url(self.environment.driver)))
            assert new_state is not None, "new_state is None"

            if new_state != state:
                return new_state
        return state

    def trace(self, domain, wait_response_seconds = 60, attempts = 3, delaying_time = 10):
        """
        Traces shop

        :param domain:                 Shop domain to trace
        :param wait_response_seconds:  Seconds to wait response from shop
        :param attempts:               Number of attempts to navigate to checkout page
        :return:                       ICrawlingStatus
        """

        result = None
        best_state_idx = -1
        time_to_sleep = 2

        for _ in range(attempts):
            self.on_tracing_started(domain)
            attempt_result = self.do_trace(domain, wait_response_seconds, delaying_time)
            self.on_tracing_finished(attempt_result)

            if isinstance(attempt_result, ProcessingStatus):
                idx = States.states.index(attempt_result.state)
                if idx > best_state_idx:
                    best_state_idx = idx
                    result = attempt_result

                # Don't need randomization if we have already navigated to checkout page
                if idx >= States.states.index(States.checkout_page):
                    break

            if not result:
                result = attempt_result
            time.sleep(time_to_sleep)
            time_to_sleep = 2 * time_to_sleep
        return result

    def do_trace(self, domain, wait_response_seconds = 60, delaying_time = 10):
        state = States.new

        context = TraceContext(domain, delaying_time, self)

        try:
            status = None

            if not self.environment.start(domain):
                return NotAvailable('Domain {} is not available'.format(domain))

            context.on_started()   
            assert context.is_started
            
            if is_domain_for_sale(self.environment.driver, domain):
                return NotAvailable('Domain {} for sale'.format(domain))

            while state != States.purchased:
                new_state = self.process_state(state, context)

                if state == new_state:
                    break

                state = new_state
                
        except:
            self._logger.exception("Unexpected exception during processing {}".format(domain))
            exception = traceback.format_exc()
            status = ProcessingStatus(state, exception)

        finally:
            if not status:
                status = ProcessingStatus(state)
            
            if context.is_started:
                context.on_finished(status)

        return status
