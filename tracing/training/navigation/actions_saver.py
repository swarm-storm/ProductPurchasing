import tempfile
import uuid
import os
import os.path
import json
from tracing.heuristic.shop_tracer import ITraceListener
from tracing.rl.actor_learner import ActionsMemory
import tracing.selenium_utils.common as common
from tracing.utils.images import *
from tracing.rl.actions import Actions
import traceback
import shutil


class ActionsFileRecorder(ITraceListener):

    def __init__(self, dataset):
        self.dataset = dataset

        self.ih = ImageHelper()
        assert not os.path.exists(dataset) or os.path.isdir(dataset), \
            "dataset path {} should be a folder".format(dataset)

        self.dataset_imgs = os.path.join(self.dataset, 'imgs')
        os.makedirs(self.dataset_imgs, exist_ok=True)

        self.dataset_meta = os.path.join(self.dataset, 'meta.jsonl')
        if not os.path.exists(self.dataset_meta):
            f = open(self.dataset_meta, 'w')
            f.close()

        self.create_tmp_files()

    def on_handler_started(self, environment, handler, state):
        self.handler = str(handler) if handler else None
        self.state_file = self.get_new_img_file()

        environment.try_switch_to_default()
        scale = common.get_scale(environment.driver)
        try:
            common.get_full_page_screenshot(environment.driver, self.state_file, scale)
        finally:
            environment.try_switch_to_frame()

        self.handlers.append([])

    def on_tracing_started(self, domain):
        self.domain = domain
        self.handlers = []

    def on_tracing_finished(self, status):
        self.flush()

    def create_tmp_files(self):
        # Create Tmp file for trace
        self.imgs_folder = tempfile.mkdtemp()

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        os.remove(self.imgs_folder)

    def get_new_img_file(self):
        fname = str(uuid.uuid4()).replace('-', '') + '.png'
        return os.path.join(self.imgs_folder, fname)


    def before_action(self, environment, control = None, state = None, handler = None, frame_idx = None):
        self.control_file = None
        self.control_label = None
        self.possible_actions = None
        self.control_type = None
        self.handler = str(handler) if handler else None
        self.frame_idx = frame_idx

        # 1. Save control image and other info
        if control is not None:
            try:
                inp = environment.get_control_as_input(control)
                self.control_file = self.get_new_img_file()
                self.ih.input2img(inp, self.control_file)

                self.control_label = control.label
                self.possible_actions = ActionsMemory.get_possible_actions(control, Actions.navigation)
                self.control_type = control.type.__class__.__name__
            except:
                traceback.print_exc()

        # 2. Save current url
        self.url = common.get_url(environment.driver)
        self.state = state

    def after_action(self, action, is_success, new_state = None):
        status = {
            'domain': self.domain,
            'url': self.url,
            'control_img': os.path.basename(self.control_file) if self.control_file else None,
            'state_img': os.path.basename(self.state_file),
            'action': action.__class__.__name__,
            'is_success': is_success,
            'possible_actions': self.possible_actions,
            'state': self.state,
            'new_state': new_state,
            'control_label': self.control_label,
            'control_type': self.control_type,
            'handler': self.handler,
            'frame_idx': self.frame_idx
        }

        self.handlers[-1].append(status)

        
    def move_file(self, fname, src_folder, dst_folder):
        src = os.path.join(src_folder, fname)
        dst = os.path.join(dst_folder, fname)

        os.rename(src, dst)

    def filter_handlers(self):
        for handler in self.handlers:
            to_return = False
            for item in handler:
                if item['action'] != 'Nothing' and item['is_success']:
                    to_return = True
                    break

            if to_return:
                yield handler

    def flush(self):
        print('started flashing for domain', self.domain)

        # Move recorded data from temp folder to dataset
        with open(self.dataset_meta, 'a') as dst:
            for handler in self.filter_handlers():
                # Saves array of controls
                state_file = None
                for control_info in handler:
                    if control_info.get('control_img'):
                        self.move_file(control_info['control_img'], self.imgs_folder, self.dataset_imgs)

                    if control_info.get('state_img'):
                        state_file = control_info['state_img']

                if state_file:
                    self.move_file(state_file, self.imgs_folder, self.dataset_imgs)

                line = json.dumps(handler)
                dst.write(line.strip() + '\n')
                dst.flush()

        # Clear folder
        shutil.rmtree(self.imgs_folder)
        self.create_tmp_files()
