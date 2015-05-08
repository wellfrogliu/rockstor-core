"""
Copyright (c) 2012-2013 RockStor, Inc. <http://rockstor.com>
This file is part of RockStor.

RockStor is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License as published
by the Free Software Foundation; either version 2 of the License,
or (at your option) any later version.

RockStor is distributed in the hope that it will be useful, but
WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program. If not, see <http://www.gnu.org/licenses/>.
"""

from rest_framework import status
from rest_framework.test import APITestCase
import mock
from mock import patch

from storageadmin.models import Pool

class PoolTests(APITestCase):
    fixtures = ['fix1.json']
    BASE_URL = '/api/pools'

    @classmethod
    def setUpClass(self):

        # post mocks
        self.patch_mount_root = patch('storageadmin.views.pool.mount_root')
        self.mock_mount_root = self.patch_mount_root.start()
        self.mock_mount_root.return_value = 'foo'

        self.patch_add_pool = patch('storageadmin.views.pool.add_pool')
        self.mock_add_pool = self.patch_add_pool.start()
        self.mock_add_pool.return_value = True

        self.patch_pool_usage = patch('storageadmin.views.pool.pool_usage')
        self.mock_pool_usage = self.patch_pool_usage.start()
        self.mock_pool_usage.return_value = (100, 10, 90)

        self.patch_btrfs_uuid = patch('storageadmin.views.pool.btrfs_uuid')
        self.mock_btrfs_uuid = self.patch_btrfs_uuid.start()
        self.mock_btrfs_uuid.return_value = 'bar'

        # put mocks (also uses pool_usage)
        self.patch_resize_pool = patch('storageadmin.views.pool.resize_pool')
        self.mock_resize_pool = self.patch_resize_pool.start()
        self.mock_resize_pool = True

        self.patch_balance_start = patch('storageadmin.views.pool.balance_start')
        self.mock_balance_start = self.patch_balance_start.start()
        self.mock_balance_start.return_value = 1

        # delete mocks
        self.patch_umount_root = patch('storageadmin.views.pool.umount_root')
        self.mock_umount_root = self.patch_umount_root.start()
        self.mock_umount_root.return_value = True

        # remount mocks
        self.patch_remount = patch('storageadmin.views.pool.remount')
        self.mock_remount = self.patch_remount.start()
        self.mock_remount.return_value = True

        # error handling run_command mocks
        self.patch_run_command = patch('storageadmin.util.run_command')
        self.mock_run_command = self.patch_run_command.start()
        self.mock_run_command.return_value = True

    @classmethod
    def tearDownClass(self):
        patch.stopall()

    def setUp(self):
        self.client.login(username='admin', password='admin')

    def test_auth(self):
        """
        unauthorized api access
        """
        self.client.logout()
        response = self.client.get(self.BASE_URL)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_get(self):
        """
        get on the base url.
        """
        response1 = self.client.get(self.BASE_URL)
        self.assertEqual(response1.status_code, status.HTTP_200_OK, msg=response1.data)

    def test_invalid_operations(self):
        """
        invalid pool operations
        1. attempt to create a pool with invalid raid level
        2. attempt to edit root pool
        """
        data = {'disks': ('sdc', 'sdd',),
                'pname': 'singlepool2',
                'raid_level': 'derp', }
        e_msg = ("Unsupported raid level. use one of: ('single', 'raid0', 'raid1', 'raid10', 'raid5', 'raid6')")
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        self.assertEqual(response.data['detail'], e_msg)

        # attempt to add disk to root pool
        data2 = {'disks': ('sdc', 'sdd',)}
        e_msg = ('Edit operations are not allowed on this Pool(rockstor_rockstor) as it contains the operating system.')
        response2 = self.client.put('%s/rockstor_rockstor/add' % self.BASE_URL, data=data2)
        self.assertEqual(response2.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response2.data)
        self.assertEqual(response2.data['detail'], e_msg)

        # get a pool that doesn't exist
        e_msg = ('Not found')
        response1 = self.client.get('%s/raid0pool' % self.BASE_URL)
        self.assertEqual(response1.status_code, status.HTTP_404_NOT_FOUND, msg=response1.data)
        self.assertEqual(response1.data['detail'], e_msg)
        
        # edit a pool that doesn't exist
        response2 = self.client.put('%s/raid0pool/add' % self.BASE_URL, data=data2)
        self.assertEqual(response2.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response2.data)
        self.assertEqual(response2.data['detail'], e_msg)

    def test_name_regex(self):
        """
        Pool name must start with a alphanumeric(a-z0-9) ' 'character and can be
        followed by any of the ' 'following characters: letter(a-z),
        digits(0-9), ' 'hyphen(-), underscore(_) or a period(.).'
        1. Test a few valid regexes (eg: pool1, Mypool, 123, etc..)
        2. Test a few invalid regexes (eg: -pool1, .pool etc..)
        """
        # valid pool names
        data = {'disks': ('sdb',),
                'pname': '123pool',
                'raid_level': 'single', }
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data['name'], '123pool')
        
        data = {'disks': ('sdc',),
                'pname': 'POOL_TEST_',
                'raid_level': 'single', }
        response2 = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response2.status_code, status.HTTP_200_OK, msg=response2.data)
        self.assertEqual(response2.data['name'], 'POOL_TEST_')

        data = {'disks': ('sdd',),
                'pname': 'Zzzz....',
                'raid_level': 'single', }        
        response3 = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response3.status_code, status.HTTP_200_OK, msg=response3.data)
        self.assertEqual(response3.data['name'], 'Zzzz....')
        
        # invalid pool names
        data['pname'] = 'Pool $'
        e_msg = ('Pool name must start with a alphanumeric(a-z0-9) character and can be followed by any of the following characters: letter(a-z), digits(0-9), hyphen(-), underscore(_) or a period(.).')
        response4 = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response4.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response4.data)
        self.assertEqual(response4.data['detail'], e_msg)

        data['pname'] = '-pool'
        response5 = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response5.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response5.data)
        self.assertEqual(response5.data['detail'], e_msg)

        data['pname'] = '.pool'
        response6 = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response6.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response6.data)
        self.assertEqual(response6.data['detail'], e_msg)

    def test_compression(self):
        """
        Compression is agnostic to name, raid and number of disks. So no need to
        test it with different types of pools. Every post & remount calls this.
        1. Create a pool with invalid compression
        2. Create a pool with zlib compression
        3. Create a pool with lzo compression
        4. change compression from zlib to lzo
        5. change compression from lzo to zlib
        6. disable zlib, enable zlib
        7. disable lzo, enable lzo
        """
        # create pool with invalid compression
        data = {'disks': ('sdc', 'sdd',),
                'pname': 'singlepool',
                'raid_level': 'single',
                'compression': 'derp'}
        e_msg = ("Unsupported compression algorithm(derp). Use one of ('lzo', 'zlib', 'no')")
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        self.assertEqual(response.data['detail'], e_msg)

        # create pool with zlib compression
        data['compression'] = 'zlib'
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data['compression'], 'zlib')
        
        # create pool with lzo compression
        data2 = {'disks': ('sde', 'sdf',),
                'pname': 'singlepool2',
                'raid_level': 'single',
                'compression': 'lzo'}
        response2 = self.client.post(self.BASE_URL, data=data2)
        self.assertEqual(response2.status_code, status.HTTP_200_OK, msg=response2.data)
        self.assertEqual(response2.data['compression'], 'lzo')
        
        # change compression from zlib to lzo
        data3 = {'compression': 'lzo'}
        response3 = self.client.put('%s/singlepool/remount' % self.BASE_URL, data=data3)
        self.assertEqual(response3.status_code, status.HTTP_200_OK, msg=response3.data)
        self.assertEqual(response3.data['compression'], 'lzo')
        
        # change compression from lzo to zlib
        data4 = {'compression': 'zlib'}
        response4 = self.client.put('%s/singlepool2/remount' % self.BASE_URL, data=data4)
        self.assertEqual(response4.status_code, status.HTTP_200_OK, msg=response4.data)
        self.assertEqual(response4.data['compression'], 'zlib')

        # disable zlib compression
        data5 = {'compression': 'no'}
        response5 = self.client.put('%s/singlepool2/remount' % self.BASE_URL, data=data5)
        self.assertEqual(response5.status_code, status.HTTP_200_OK, msg=response5.data)
        self.assertEqual(response5.data['compression'], 'no')

        # enable zlib compression
        response6 = self.client.put('%s/singlepool2/remount' % self.BASE_URL, data=data4)
        self.assertEqual(response6.status_code, status.HTTP_200_OK, msg=response6.data)
        self.assertEqual(response6.data['compression'], 'zlib')

        # disable lzo compression
        response7 = self.client.put('%s/singlepool/remount' % self.BASE_URL, data=data5)
        self.assertEqual(response7.status_code, status.HTTP_200_OK, msg=response7.data)
        self.assertEqual(response7.data['compression'], 'no')

        # enable lzo compression
        response8 = self.client.put('%s/singlepool/remount' % self.BASE_URL, data=data3)
        self.assertEqual(response8.status_code, status.HTTP_200_OK, msg=response8.data)
        self.assertEqual(response8.data['compression'], 'lzo')

    def test_mount_options(self):
        """
        Mount options are agnostic to other parameters as in compression.
        Mount validations are called every post & remount operation
        1. test invalid options (see allowed_options in the pool.py(view))
        2. test all valid options
        3. test compress-force options
        4. test invalid compress-force
        """
        # test invalid mount options
        data = {'disks': ('sde', 'sdf',),
                'pname': 'singleton',
                'raid_level': 'single',
                'compression': 'zlib',
                'mnt_options': 'alloc_star'}
        e_msg = ("mount option(alloc_star) not allowed. Make sure there are no whitespaces in the input. Allowed options: ['fatal_errors', '', 'thread_pool', 'max_inline', 'ssd_spread', 'clear_cache', 'inode_cache', 'nodatacow', 'noatime', 'nodatasum', 'alloc_start', 'noacl', 'compress-force', 'space_cache', 'ssd', 'discard', 'commit', 'autodefrag', 'metadata_ratio', 'nospace_cache']")
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        self.assertEqual(response.data['detail'], e_msg)

        data['mnt_options'] = 'alloc_start'
        e_msg = ('Value for mount option(alloc_start) must be an integer')
        response2 = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response2.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response2.data)
        self.assertEqual(response2.data['detail'], e_msg)

        data['mnt_options'] = 'alloc_start=derp'
        response3 = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response3.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response3.data)
        self.assertEqual(response3.data['detail'], e_msg)

        # test all valid mount options
        data['mnt_options'] = 'fatal_errors'
        response3 = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response3.status_code, status.HTTP_200_OK, msg=response3.data)
        self.assertEqual(response3.data['mnt_options'], 'fatal_errors')

        valid_mnt_options = 'fatal_errors,thread_pool=1,max_inline=2,ssd_spread,clear_cache,inode_cache,nodatacow,noatime,nodatasum,alloc_start=3,noacl,space_cache,ssd,discard,commit=4,autodefrag,metadata_ratio=5,nospace_cache'
        data2 = {'mnt_options': valid_mnt_options}
        response3 = self.client.put('%s/singleton/remount' % self.BASE_URL, data=data2)
        self.assertEqual(response3.status_code, status.HTTP_200_OK, msg=response3.data)
        self.assertEqual(response3.data['mnt_options'], valid_mnt_options)

        # test compress-force options
        data2 = {'mnt_options': 'compress-force=no'}
        response3 = self.client.put('%s/singleton/remount' % self.BASE_URL, data=data2)
        self.assertEqual(response3.status_code, status.HTTP_200_OK, msg=response3.data)
        self.assertEqual(response3.data['mnt_options'], 'compress-force=no')
        self.assertEqual(response3.data['compression'], 'no')

        data2 = {'mnt_options': 'compress-force=zlib'}
        response3 = self.client.put('%s/singleton/remount' % self.BASE_URL, data=data2)
        self.assertEqual(response3.status_code, status.HTTP_200_OK, msg=response3.data)
        self.assertEqual(response3.data['mnt_options'], 'compress-force=zlib')
        # TODO should be:
        # self.assertEqual(response3.data['compression'], 'zlib')
        self.assertEqual(response3.data['compression'], 'no')

        data2 = {'mnt_options': 'compress-force=lzo'}
        response3 = self.client.put('%s/singleton/remount' % self.BASE_URL, data=data2)
        self.assertEqual(response3.status_code, status.HTTP_200_OK, msg=response3.data)
        self.assertEqual(response3.data['mnt_options'], 'compress-force=lzo')
        # TODO should be:
        # self.assertEqual(response3.data['compression'], 'lzo')
        self.assertEqual(response3.data['compression'], 'no')

        # test invalid compress-force
        data2 = {'mnt_options': 'compress-force=1'}
        e_msg = ("compress-force is only allowed with ('lzo', 'zlib', 'no')")
        response3 = self.client.put('%s/singleton/remount' % self.BASE_URL, data=data2)
        self.assertEqual(response3.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response3.data)
        self.assertEqual(response3.data['detail'], e_msg)

    def test_single_crud(self):

        """
        test pool crud ops with 'single' raid config. single can be used to create a pool
        with any number of drives but drives cannot be removed.
        1. create a pool with 0 disks
        2. create a pool with 1 disk
        3. create a pool with 2 disks
        4. create a pool with a duplicate name
        5. add 2 disks to pool
        6. attempt to add a disk that doesn't exist
        7. remove 2 disks from pool
        8. delete pool
        """

        # create pool with 0 disks
        data = {'pname': 'singlepool',
                'raid_level': 'single', }
        e_msg = ("'NoneType' object is not iterable")
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        self.assertEqual(response.data['detail'], e_msg)

        # create pool with 1 disk
        data['disks'] = ('sdb',)
        response2 = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response2.status_code, status.HTTP_200_OK, msg=response2.data)
        self.assertEqual(response2.data['name'], 'singlepool')
        self.assertEqual(response2.data['raid'], 'single')
        self.mock_btrfs_uuid.assert_called_with('sdb')
        self.assertEqual(len(response2.data['disks']), 1)

        # create pool with 2 disks
        data = {'disks': ('sdc', 'sdd',),
                'pname': 'singlepool2',
                'raid_level': 'single', }
        response3 = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response3.status_code, status.HTTP_200_OK, msg=response3.data)
        self.assertEqual(response3.data['name'], 'singlepool2')
        self.assertEqual(response3.data['raid'], 'single')
        self.mock_btrfs_uuid.assert_called_with('sdc')
        self.assertEqual(len(response3.data['disks']), 2)

        # create a pool with a duplicate name
        e_msg = ('Pool(singlepool2) already exists. Choose a different name')
        response4 = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response4.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response4.data)
        self.assertEqual(response4.data['detail'], e_msg)

        # add 2 disks
        data2 = {'disks': ('sdf', 'sdg',), }
        response5 = self.client.put('%s/singlepool2/add' % self.BASE_URL, data=data2)
        self.assertEqual(response5.status_code, status.HTTP_200_OK, msg=response5.data)
        self.assertEqual(len(response5.data['disks']), 4)

        # attempt to add disk that does not exist
        data3 = {'disks': ('derp'), }
        e_msg = ('Disk(d) does not exist')
        response5 = self.client.put('%s/singlepool2/add' % self.BASE_URL, data=data3)
        self.assertEqual(response5.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response5.data)
        self.assertEqual(response5.data['detail'], e_msg)

        # remove 2 disks
        e_msg = ('Disks cannot be removed from a pool with this raid(single) configuration')
        response6 = self.client.put('%s/singlepool2/remove' % self.BASE_URL, data=data2)
        self.assertEqual(response6.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response6.data)
        self.assertEqual(response6.data['detail'], e_msg)

        # delete pool
        response7 = self.client.delete('%s/singlepool2' % self.BASE_URL)
        self.assertEqual(response7.status_code, status.HTTP_200_OK, msg=response7.data)
        self.mock_umount_root.assert_called_with('/mnt2/singlepool2')

    def test_raid0_crud(self):
        """
        test pool crud ops with 'raid0' raid config. raid0 can be used to create a pool
        with atleast 2 disks & disks cannot be removed
        1. attempt to create a pool with 1 disk
        2. create a pool with 2 disks
        3. get pool
        4. add disk to pool
        5. add disks & change riad config
        6. attempt remove disk from pool
        7. delete pool
        """
        data = {'disks': ('sdb',),
                'pname': 'raid0pool',
                'raid_level': 'raid0', }

        # create pool with 1 disk
        e_msg = ('At least two disks are required for the raid level: raid0')
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        self.assertEqual(response.data['detail'], e_msg)

        # create pool with 2 disks
        data['disks'] = ('sdb', 'sdc',)
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data['name'], 'raid0pool')
        self.assertEqual(response.data['raid'], 'raid0')
        self.mock_btrfs_uuid.assert_called_with('sdb')
        # disk length assert was failing... list is 'empty'... post function was not adding disks to the pool (atleast not saving them)... appears they WERE added but then dropped it on DB call
        # solution: assigned disks to the pool & saved each disk
        self.assertEqual(len(response.data['disks']), 2)

        # get pool
        response1 = self.client.get('%s/raid0pool' % self.BASE_URL)
        self.assertEqual(response1.status_code, status.HTTP_200_OK, msg=response1.data)
        self.assertEqual(response.data['name'], 'raid0pool')

        # get pool queryset, sort by usage
        # TODO
        # AttributeError: 'Pool' object has no attribute 'cur_usage'
        # response1 = self.client.get('%s?sortby=usage' % self.BASE_URL)
        # self.assertEqual(response1.status_code, status.HTTP_200_OK, msg=response1.data)
        # self.assertEqual(response.data, 'raid0pool')

        # add 1 disk
        data2 = {'disks': ('sdd',)}
        response2 = self.client.put('%s/raid0pool/add' % self.BASE_URL, data=data2)
        self.assertEqual(response2.status_code, status.HTTP_200_OK, msg=response2.data)
        self.assertEqual(len(response2.data['disks']), 3)

        # remove disks
        response3 = self.client.put('%s/raid0pool/remove' % self.BASE_URL, data=data2)
        self.assertEqual(response3.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response3.data)
        e_msg = ('Disks cannot be removed from a pool with this raid(raid0) configuration')
        self.assertEqual(response3.data['detail'], e_msg)

        # add 3 disks & change raid_level
        # TODO how to mimic raid migration? won't allow... 'A Balance process is already running for this pool'
        # data3 = {'disks': ('sde', 'sdf', 'sdg',),
        #          'raid_level': 'raid1', }
        # response4 = self.client.put('%s/raid0pool/add' % self.BASE_URL, data=data3)
        # self.assertEqual(response4.status_code, status.HTTP_200_OK, msg=response4.data)
        # self.assertEqual(len(response4.data['disks']), 6)
        # self.assertEqual(response4.data['raid_level'], 'raid1')

        # add 3 disks & change raid_level
        data3 = {'disks': ('sde', 'sdf', 'sdg',),
                 'raid_level': 'raid1', }
        e_msg = 'A Balance process is already running for this pool(raid0pool). Resize is not supported during a balance process.'
        response4 = self.client.put('%s/raid0pool/add' % self.BASE_URL, data=data3)
        self.assertEqual(response4.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response4.data)
        self.assertEqual(response4.data['detail'], e_msg)

        # delete pool
        response5 = self.client.delete('%s/raid0pool' % self.BASE_URL)
        self.assertEqual(response5.status_code, status.HTTP_200_OK, msg=response5.data)
        self.mock_umount_root.assert_called_with('/mnt2/raid0pool')

    def test_raid1_crud(self):
        """
        test pool crud ops with 'raid1' raid config. raid1 can be used to create a pool
        with atleast 2 disks & disks can be removed 1 at a time
        1. attempt to create a pool with 1 disk
        2. create a pool with 4 disks
        3. add 2 disks to pool
        4. attempt to remove 2 disks from pool
        5. remove 1 disk from pool
        6. delete pool
        """
        data = {'disks': ('sdb',),
                'pname': 'raid1pool',
                'raid_level': 'raid1', }

        # create pool with 1 disk
        e_msg = ('At least two disks are required for the raid level: raid1')
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        self.assertEqual(response.data['detail'], e_msg)

        # create pool with 4 disks
        data['disks'] = ('sdb', 'sdc', 'sdd', 'sde',)
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data['name'], 'raid1pool')
        self.assertEqual(response.data['raid'], 'raid1')
        self.mock_btrfs_uuid.assert_called_with('sdb')
        self.assertEqual(len(response.data['disks']), 4)

        # add 2 disks
        data2 = {'disks': ('sdf', 'sdg',), }
        response2 = self.client.put('%s/raid1pool/add' % self.BASE_URL, data=data2)
        self.assertEqual(response2.status_code, status.HTTP_200_OK, msg=response2.data)
        self.assertEqual(len(response2.data['disks']), 6)

        # remove 2 disks
        response3 = self.client.put('%s/raid1pool/remove' % self.BASE_URL, data=data2)
        self.assertEqual(response3.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response3.data)
        e_msg = ('Only one disk can be removed at once from this pool because of its raid configuration(raid1)')
        self.assertEqual(response3.data['detail'], e_msg)

        # remove 1 disk
        data3 = {'disks': ('sde',), }
        response4 = self.client.put('%s/raid1pool/remove' % self.BASE_URL, data=data3)
        self.assertEqual(response4.status_code, status.HTTP_200_OK, msg=response4.data)
        self.assertEqual(len(response4.data['disks']), 5)

        # delete pool
        response5 = self.client.delete('%s/raid1pool' % self.BASE_URL)
        self.assertEqual(response5.status_code, status.HTTP_200_OK, msg=response5.data)
        self.mock_umount_root.assert_called_with('/mnt2/raid1pool')

    def test_raid10_crud(self):
        """
        test pool crud ops with 'raid10' raid config. raid10 can be used to create a pool
        with atleast 4 disks & must have an even number of disks.
        1. attempt to create a pool with 1 disk
        2. attempt to create a pool with 5 disks
        3. create a pool with 4 disks
        4. attempt to add 1 disk
        5. add 2 disks to pool
        6. remove 2 disks
        7. attempt to remove 1 disk from pool
        8. delete pool
        """
        data = {'disks': ('sdb',),
                'pname': 'raid10pool',
                'raid_level': 'raid10', }

        # create pool with 1 disk
        e_msg = ('A minimum of Four drives are required for the raid level: raid10')
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        self.assertEqual(response.data['detail'], e_msg)

        # create pool with odd disks
        data['disks'] = ('sdb', 'sdc', 'sdd', 'sde', 'sdf',)
        e_msg = ('Even number of drives are required for the raid level: raid10')
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        self.assertEqual(response.data['detail'], e_msg)

        # create pool with 4 disks
        data['disks'] = ('sdb', 'sdc', 'sdd', 'sde',)
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data['name'], 'raid10pool')
        self.assertEqual(response.data['raid'], 'raid10')
        self.mock_btrfs_uuid.assert_called_with('sdb')
        self.assertEqual(len(response.data['disks']), 4)

        # add 1 disk
        data2 = {'disks': ('sdf',), }
        response1 = self.client.put('%s/raid10pool/add' % self.BASE_URL, data=data2)
        self.assertEqual(response1.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response1.data)
        e_msg = ('raid10 requires an even number of drives. Total provided = 1')
        self.assertEqual(response1.data['detail'], e_msg)

        # add 2 disks
        data2 = {'disks': ('sdf', 'sdg',), }
        response2 = self.client.put('%s/raid10pool/add' % self.BASE_URL, data=data2)
        self.assertEqual(response2.status_code, status.HTTP_200_OK, msg=response2.data)
        self.assertEqual(len(response2.data['disks']), 6)

        # remove 2 disks
        response3 = self.client.put('%s/raid10pool/remove' % self.BASE_URL, data=data2)
        self.assertEqual(response3.status_code, status.HTTP_200_OK, msg=response3.data)
        self.assertEqual(len(response3.data['disks']), 4)

        # remove 1 disk
        data3 = {'disks': ('sde',), }
        response4 = self.client.put('%s/raid10pool/remove' % self.BASE_URL, data=data3)
        self.assertEqual(response4.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response4.data)
        e_msg = ('Only two disks can be removed at once from this pool because of its raid configuration(raid10)')
        self.assertEqual(response4.data['detail'], e_msg)

        # delete pool
        response5 = self.client.delete('%s/raid10pool' % self.BASE_URL)
        self.assertEqual(response5.status_code, status.HTTP_200_OK, msg=response5.data)
        self.mock_umount_root.assert_called_with('/mnt2/raid10pool')

    def test_raid5_crud(self):
        """
        test pool crud ops with 'raid5' raid config. raid5 can be used to create a pool
        with at least 3 disks & disks cannot be removed
        1. attempt to create a pool with 1 disk
        2. create a pool with 4 disks
        3. add 2 disks to pool
        4. attempt to remove 2 disks
        5. delete pool
        """
        data = {'disks': ('sdb',),
                'pname': 'raid5pool',
                'raid_level': 'raid5', }

        # create pool with 1 disk
        e_msg = ('Three or more disks are required for the raid level: raid5')
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        self.assertEqual(response.data['detail'], e_msg)

        # create pool with 4 disks
        data['disks'] = ('sdb', 'sdc', 'sdd', 'sde',)
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data['name'], 'raid5pool')
        self.assertEqual(response.data['raid'], 'raid5')
        self.mock_btrfs_uuid.assert_called_with('sdb')
        self.assertEqual(len(response.data['disks']), 4)

        # add 2 disks
        data2 = {'disks': ('sdf', 'sdg',), }
        response2 = self.client.put('%s/raid5pool/add' % self.BASE_URL, data=data2)
        self.assertEqual(response2.status_code, status.HTTP_200_OK, msg=response2.data)
        self.assertEqual(len(response2.data['disks']), 6)

        # remove 2 disks
        response4 = self.client.put('%s/raid5pool/remove' % self.BASE_URL, data=data2)
        self.assertEqual(response4.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response4.data)
        e_msg = ('Disk removal is not supported for pools with raid5/6 configuration')
        self.assertEqual(response4.data['detail'], e_msg)

        # delete pool
        response5 = self.client.delete('%s/raid5pool' % self.BASE_URL)
        self.assertEqual(response5.status_code, status.HTTP_200_OK, msg=response5.data)
        self.mock_umount_root.assert_called_with('/mnt2/raid5pool')

    def test_raid6_crud(self):
        """
        test pool crud ops with 'raid6' raid config. raid6 can be used to create a pool
        with at least 4 disks & disks cannot be removed
        1. attempt to create a pool with 1 disk
        2. create a pool with 4 disks
        3. add 2 disks to pool
        4. attempt to remove 2 disks
        5. delete pool
        """
        data = {'disks': ('sdb',),
                'pname': 'raid6pool',
                'raid_level': 'raid6', }

        # create pool with 1 disk
        e_msg = ('Four or more disks are required for the raid level: raid6')
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response.data)
        self.assertEqual(response.data['detail'], e_msg)

        # create pool with 4 disks
        data['disks'] = ('sdb', 'sdc', 'sdd', 'sde',)
        response = self.client.post(self.BASE_URL, data=data)
        self.assertEqual(response.status_code, status.HTTP_200_OK, msg=response.data)
        self.assertEqual(response.data['name'], 'raid6pool')
        self.assertEqual(response.data['raid'], 'raid6')
        self.mock_btrfs_uuid.assert_called_with('sdb')
        self.assertEqual(len(response.data['disks']), 4)

        # add 2 disks
        data2 = {'disks': ('sdf', 'sdg',), }
        response2 = self.client.put('%s/raid6pool/add' % self.BASE_URL, data=data2)
        self.assertEqual(response2.status_code, status.HTTP_200_OK, msg=response2.data)
        self.assertEqual(len(response2.data['disks']), 6)

        # remove 2 disks
        response4 = self.client.put('%s/raid6pool/remove' % self.BASE_URL, data=data2)
        self.assertEqual(response4.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR, msg=response4.data)
        e_msg = ('Disk removal is not supported for pools with raid5/6 configuration')
        self.assertEqual(response4.data['detail'], e_msg)

        # delete pool
        response5 = self.client.delete('%s/raid6pool' % self.BASE_URL)
        self.assertEqual(response5.status_code, status.HTTP_200_OK, msg=response5.data)
        self.mock_umount_root.assert_called_with('/mnt2/raid6pool')