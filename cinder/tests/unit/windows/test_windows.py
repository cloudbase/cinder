# Copyright 2012 Pedro Navarro Perez
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""
Unit tests for Windows Server 2012 OpenStack Cinder volume driver
"""


import os
import shutil
import tempfile

from mox3 import mox
from oslo_config import cfg
from oslo_utils import fileutils

from cinder.image import image_utils
from cinder import test
from cinder.tests.unit.windows import db_fakes
from cinder.volume import configuration as conf
from cinder.volume.drivers.windows import constants
from cinder.volume.drivers.windows import imagecache
from cinder.volume.drivers.windows import vhdutils
from cinder.volume.drivers.windows import windows
from cinder.volume.drivers.windows import windows_utils

CONF = cfg.CONF


class TestWindowsDriver(test.TestCase):

    def __init__(self, method):
        super(TestWindowsDriver, self).__init__(method)

    def setUp(self):
        self.lun_path_tempdir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.lun_path_tempdir)

        super(TestWindowsDriver, self).setUp()
        self.flags(
            windows_iscsi_lun_path=self.lun_path_tempdir,
        )
        self._setup_stubs()
        configuration = conf.Configuration(None)
        configuration.append_config_values(windows.windows_opts)
        self._driver = windows.WindowsDriver(configuration=configuration)
        self._driver.do_setup({})

    def _setup_stubs(self):

        def fake_wutils__init__(self):
            pass

        windows_utils.WindowsUtils.__init__ = fake_wutils__init__

    def fake_local_path(self, volume):
        return os.path.join(CONF.windows_iscsi_lun_path,
                            str(volume['name']) + ".vhd")

    def _fake_check_min_windows_version(self, major, minor, build=0):
        return True

    def test_check_for_setup_errors(self):
        drv = self._driver

        self.flags(use_cow_images=True, group='imagecache')

        self.mox.StubOutWithMock(windows_utils.WindowsUtils,
                                 'check_for_setup_error')
        self.stubs.Set(windows_utils.WindowsUtils,
                       'check_min_windows_version',
                       self._fake_check_min_windows_version)

        windows_utils.WindowsUtils.check_for_setup_error()
        windows_utils.WindowsUtils.check_min_windows_version(6, 3)

        self.mox.ReplayAll()

        drv.check_for_setup_error()

    def test_create_volume(self):
        drv = self._driver
        vol = db_fakes.get_fake_volume_info()

        self.stubs.Set(drv, 'local_path', self.fake_local_path)

        self.mox.StubOutWithMock(windows_utils.WindowsUtils,
                                 'create_volume')

        windows_utils.WindowsUtils.create_volume(self.fake_local_path(vol),
                                                 vol['name'], vol['size'])

        self.mox.ReplayAll()

        drv.create_volume(vol)

    def test_delete_volume(self):
        """delete_volume simple test case."""
        drv = self._driver

        vol = db_fakes.get_fake_volume_info()

        self.mox.StubOutWithMock(drv, 'local_path')
        drv.local_path(vol).AndReturn(self.fake_local_path(vol))

        self.mox.StubOutWithMock(windows_utils.WindowsUtils,
                                 'delete_volume')
        windows_utils.WindowsUtils.delete_volume(vol['name'],
                                                 self.fake_local_path(vol))
        self.mox.ReplayAll()

        drv.delete_volume(vol)

    def test_create_snapshot(self):
        drv = self._driver
        self.mox.StubOutWithMock(windows_utils.WindowsUtils,
                                 'create_snapshot')
        volume = db_fakes.get_fake_volume_info()
        snapshot = db_fakes.get_fake_snapshot_info()

        self.stubs.Set(drv, 'local_path', self.fake_local_path(snapshot))

        windows_utils.WindowsUtils.create_snapshot(volume['name'],
                                                   snapshot['name'])

        self.mox.ReplayAll()

        drv.create_snapshot(snapshot)

    def test_create_volume_from_snapshot(self):
        drv = self._driver

        snapshot = db_fakes.get_fake_snapshot_info()
        volume = db_fakes.get_fake_volume_info()

        self.mox.StubOutWithMock(windows_utils.WindowsUtils,
                                 'create_volume_from_snapshot')
        windows_utils.WindowsUtils.\
            create_volume_from_snapshot(volume, snapshot['name'])

        self.mox.ReplayAll()

        drv.create_volume_from_snapshot(volume, snapshot)

    def test_delete_snapshot(self):
        drv = self._driver

        snapshot = db_fakes.get_fake_snapshot_info()

        self.mox.StubOutWithMock(windows_utils.WindowsUtils,
                                 'delete_snapshot')
        windows_utils.WindowsUtils.delete_snapshot(snapshot['name'])

        self.mox.ReplayAll()

        drv.delete_snapshot(snapshot)

    def _test_create_export(self, chap_enabled=False):
        drv = self._driver
        volume = db_fakes.get_fake_volume_info()
        initiator_name = "%s%s" % (CONF.iscsi_target_prefix, volume['name'])
        fake_chap_username = 'fake_chap_username'
        fake_chap_password = 'fake_chap_password'

        self.flags(use_chap_auth=chap_enabled)
        self.flags(chap_username=fake_chap_username)
        self.flags(chap_password=fake_chap_password)

        self.mox.StubOutWithMock(windows_utils.WindowsUtils,
                                 'add_disk_to_target')
        self.mox.StubOutWithMock(windows_utils.WindowsUtils,
                                 'create_iscsi_target')
        self.mox.StubOutWithMock(windows_utils.WindowsUtils,
                                 'set_chap_credentials')
        self.mox.StubOutWithMock(self._driver,
                                 'remove_export')

        self._driver.remove_export(mox.IgnoreArg(), mox.IgnoreArg())
        windows_utils.WindowsUtils.create_iscsi_target(initiator_name)

        if chap_enabled:
            windows_utils.WindowsUtils.set_chap_credentials(
                mox.IgnoreArg(),
                fake_chap_username,
                fake_chap_password)

        windows_utils.WindowsUtils.add_disk_to_target(volume['name'],
                                                      initiator_name)

        self.mox.ReplayAll()

        export_info = drv.create_export(None, volume, {})

        self.assertEqual(initiator_name, export_info['provider_location'])
        if chap_enabled:
            expected_provider_auth = ' '.join(('CHAP',
                                               fake_chap_username,
                                               fake_chap_password))
            self.assertEqual(expected_provider_auth,
                             export_info['provider_auth'])

    def test_create_export_chap_disabled(self):
        self._test_create_export()

    def test_create_export_chap_enabled(self):
        self._test_create_export(chap_enabled=True)

    def test_initialize_connection(self):
        drv = self._driver

        volume = db_fakes.get_fake_volume_info()
        initiator_name = "%s%s" % (CONF.iscsi_target_prefix, volume['name'])

        connector = db_fakes.get_fake_connector_info()

        self.mox.StubOutWithMock(windows_utils.WindowsUtils,
                                 'associate_initiator_with_iscsi_target')
        windows_utils.WindowsUtils.associate_initiator_with_iscsi_target(
            volume['provider_location'], initiator_name, )

        self.mox.StubOutWithMock(windows_utils.WindowsUtils,
                                 'get_host_information')
        windows_utils.WindowsUtils.get_host_information(
            volume, volume['provider_location'])

        self.mox.ReplayAll()

        drv.initialize_connection(volume, connector)

    def test_terminate_connection(self):
        drv = self._driver

        volume = db_fakes.get_fake_volume_info()
        initiator_name = "%s%s" % (CONF.iscsi_target_prefix, volume['name'])
        connector = db_fakes.get_fake_connector_info()

        self.mox.StubOutWithMock(windows_utils.WindowsUtils,
                                 'delete_iscsi_target')
        windows_utils.WindowsUtils.delete_iscsi_target(
            initiator_name, volume['provider_location'])

        self.mox.ReplayAll()

        drv.terminate_connection(volume, connector)

    def test_remove_export(self):
        drv = self._driver

        volume = db_fakes.get_fake_volume_info()

        target_name = volume['provider_location']

        self.mox.StubOutWithMock(windows_utils.WindowsUtils,
                                 'remove_iscsi_target')
        windows_utils.WindowsUtils.remove_iscsi_target(target_name)

        self.mox.ReplayAll()

        drv.remove_export(None, volume)

    def test_copy_image_to_volume(self):
        """resize_image common case usage."""
        drv = self._driver

        volume = db_fakes.get_fake_volume_info()

        fake_get_supported_type = lambda x: constants.VHD_TYPE_FIXED
        self.stubs.Set(drv, 'local_path', self.fake_local_path)
        self.stubs.Set(windows_utils.WindowsUtils, 'get_supported_vhd_type',
                       fake_get_supported_type)

        self.mox.StubOutWithMock(os, 'unlink')
        self.mox.StubOutWithMock(imagecache.WindowsImageCache, 'get_image')
        self.mox.StubOutWithMock(windows_utils.WindowsUtils,
                                 'change_disk_status')

        fake_volume_path = self.fake_local_path(volume)

        windows_utils.WindowsUtils.change_disk_status(volume['name'],
                                                      False)
        os.unlink(mox.IsA(str))
        imagecache.WindowsImageCache.get_image(
            None, None, None, fake_volume_path, 'vhd', volume['size'],
            image_subformat=constants.VHD_SUBFORMAT_FIXED)
        windows_utils.WindowsUtils.change_disk_status(volume['name'],
                                                      True)

        self.mox.ReplayAll()

        drv.copy_image_to_volume(None, volume, None, None)

    def _test_copy_volume_to_image(self, supported_format):
        drv = self._driver

        vol = db_fakes.get_fake_volume_info()

        image_meta = db_fakes.get_fake_image_meta()

        fake_get_supported_format = lambda x: supported_format

        self.stubs.Set(os.path, 'exists', lambda x: False)
        self.stubs.Set(drv, 'local_path', self.fake_local_path)
        self.stubs.Set(windows_utils.WindowsUtils, 'get_supported_format',
                       fake_get_supported_format)

        self.mox.StubOutWithMock(fileutils, 'ensure_tree')
        self.mox.StubOutWithMock(fileutils, 'delete_if_exists')
        self.mox.StubOutWithMock(image_utils, 'upload_volume')
        self.mox.StubOutWithMock(windows_utils.WindowsUtils, 'copy_vhd_disk')
        self.mox.StubOutWithMock(vhdutils.VHDUtils, 'convert_vhd')

        fileutils.ensure_tree(CONF.image_conversion_dir)
        temp_vhd_path = os.path.join(CONF.image_conversion_dir,
                                     str(image_meta['id']) + "." +
                                     supported_format)
        upload_image = temp_vhd_path

        windows_utils.WindowsUtils.copy_vhd_disk(self.fake_local_path(vol),
                                                 temp_vhd_path)
        if supported_format == 'vhdx':
            upload_image = upload_image[:-1]
            vhdutils.VHDUtils.convert_vhd(temp_vhd_path, upload_image,
                                          constants.VHD_TYPE_DYNAMIC)

        image_utils.upload_volume(None, None, image_meta, upload_image, 'vhd')

        fileutils.delete_if_exists(temp_vhd_path)
        fileutils.delete_if_exists(upload_image)

        self.mox.ReplayAll()

        drv.copy_volume_to_image(None, vol, None, image_meta)

    def test_copy_volume_to_image_using_vhd(self):
        self._test_copy_volume_to_image('vhd')

    def test_copy_volume_to_image_using_vhdx(self):
        self._test_copy_volume_to_image('vhdx')

    def test_create_cloned_volume(self):
        drv = self._driver

        volume = db_fakes.get_fake_volume_info()
        volume_cloned = db_fakes.get_fake_volume_info_cloned()
        new_vhd_path = self.fake_local_path(volume)
        src_vhd_path = self.fake_local_path(volume_cloned)

        self.mox.StubOutWithMock(windows_utils.WindowsUtils,
                                 'copy_vhd_disk')
        self.mox.StubOutWithMock(windows_utils.WindowsUtils,
                                 'import_wt_disk')
        self.mox.StubOutWithMock(windows_utils.WindowsUtils,
                                 'extend_vhd_if_needed')

        self.stubs.Set(drv, 'local_path', self.fake_local_path)

        windows_utils.WindowsUtils.copy_vhd_disk(src_vhd_path,
                                                 new_vhd_path)
        windows_utils.WindowsUtils.extend_vhd_if_needed(new_vhd_path,
                                                        volume['size'])
        windows_utils.WindowsUtils.import_wt_disk(new_vhd_path,
                                                  volume['name'])

        self.mox.ReplayAll()

        drv.create_cloned_volume(volume, volume_cloned)

    def test_extend_volume(self):
        drv = self._driver

        volume = db_fakes.get_fake_volume_info()

        TEST_VOLUME_ADDITIONAL_SIZE_MB = 1024
        TEST_VOLUME_ADDITIONAL_SIZE_GB = 1

        self.mox.StubOutWithMock(windows_utils.WindowsUtils, 'extend')

        windows_utils.WindowsUtils.extend(volume['name'],
                                          TEST_VOLUME_ADDITIONAL_SIZE_MB)

        new_size = volume['size'] + TEST_VOLUME_ADDITIONAL_SIZE_GB

        self.mox.ReplayAll()

        drv.extend_volume(volume, new_size)
