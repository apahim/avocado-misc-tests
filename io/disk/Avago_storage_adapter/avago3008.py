#!/usr/bin/env python

# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.
#
# See LICENSE for more details.
#
#
# Copyright: 2016 IBM
# Author: Venkat Rao B <vrbagal1@linux.vnet.ibm.com>


"""
This script will list all the adapter connected to the system.
"""


import time
from avocado import Test
from avocado.utils import process
from avocado import main


class Avago3008(Test):

    """
    This script lists all the LSI adapters attached on the machine
    """

    def setUp(self):

        """
        Lists all available Avago adapters (does not need ctlr #>
        """

        self.controller = int(self.params.get('controller', default='0'))
        self.raidlevel = str(self.params.get('raidlevel', default='0'))
        self.disk = str(self.params.get('disk')).split(" ")
        self.spare = str(self.params.get('spare'))
        self.size = int(self.params.get('size', default='max'))
        if not self.disk:
            self.skip("Please provide disks to run the tests")
        self.number_of_disk = len(self.disk)

        self.dict_raid = {'raid0': [2, None, None], 'raid1': [2, 2, None],
                          'raid1e': [3, None, None],
                          'raid10': [4, None, 'Even']}

        self.value = self.dict_raid[self.raidlevel]
        if self.number_of_disk < self.value[0]:
            self.skip("please give enough drives to perform the test")

        if self.value[1] is not None:
            self.disk = self.disk[0:self.value[1]]

        if self.value[2] == 'Even':
            if self.number_of_disk % 2 != 0:
                self.disk = self.disk[:-1]
        self.raid_disk = " ".join(self.disk).strip(" ")

    def test_run(self):

        """
        Decides which functions to run for given raid_level
        """

        cmd = "echo -e 'YES\nNO' | ./sas3ircu %d delete" \
              % (self.controller)
        if process.system(cmd, ignore_status=True, shell=True) != 0:
            self.fail("Unable to clear entire configuration before starting")
        if self.raidlevel == 'raid0':
            self.basictest()
        else:
            self.extensivetest()

    def basictest(self):

        """
        This function does only create and delete Raid
        """
        self.adapterdetails()
        self.createraid()
        self.adapter_status("Volume state")
        self.adapterdetails()
        self.deleteraid()
        self.adapter_status("Volume state")
        self.logir()

    def extensivetest(self):

        """
        Lists all the LSI adapters attached to the mahcine
        :return:
        """

        self.adapterlist()
        self.adapterdetails()
        self.createraid()
        self.backgroundinit()
        self.adapterdetails()
        self.adapter_status("Volume state")
        self.set_online_offline("offline")
        self.set_online_offline("online")
        for _ in range(0, 5):
            for state in ['offline', 'online']:
                self.set_online_offline(state)
                time.sleep(10)
        if self.spare:
            self.hotspare()
        self.rebuild()
        self.consistcheck()
        self.deleteraid()
        self.logir()
        self.adapterdetails()
        self.adapter_status("Volume state")

    def adapterlist(self):

        """
        Lists all the LSI adapters attached to the mahcine
        :return:
        """
        cmd = "./sas3ircu list"
        if process.system(cmd, ignore_status=True, shell=True) != 0:
            self.fail("Failed to list all the Avogo adapters")

    def adapterdetails(self):

        """
        Display controller, volume and physical device info
        """

        cmd = "./sas3ircu %d display" % self.controller
        if process.system(cmd, ignore_status=True, shell=True) != 0:
            self.fail("Failed to display details of drives and VR vloumes")

    def createraid(self):

        """
        This function creates raid array
        """
        cmd = "./sas3ircu %d create %s %s %s vr1 noprompt" \
              % (self.controller, self.raidlevel, self.size, self.raid_disk)
        if process.system(cmd, ignore_status=True, shell=True) != 0:
            self.fail("Failed to create raid on the drives")

    def hotspare(self):

        """
        This is a helper function to create hot-spare
        """
        cmd = "echo -e 'YES\nNO' | ./sas3ircu %d hotspare %s" \
            % (self.controller, self.spare)
        if process.system(cmd, ignore_status=True, shell=True) != 0:
            self.fail("Failed to set hotspare drive")

    def backgroundinit(self):

        """
        Checks if BGI starts automatically, and if so waits
        till it is completed
        """
        self.sleepfunction()

    def consistcheck(self):

        """
        This function starts CC on a Raid array
        """
        cmd = "./sas3ircu %d constchk %d noprompt" \
            % (self.controller, self.volumeid())
        if process.system(cmd, ignore_status=True, shell=True) != 0:
            self.fail("Failed to start CC on raid array VR1")
        self.sleepfunction()

    def logir(self):

        """
        This function stores all the IR logs
        """
        cmd = "./sas3ircu %d logir upload" % self.controller
        if process.system(cmd, ignore_status=True, shell=True) != 0:
            self.fail("Failed to upload the logs")
        cmd = "./sas3ircu %d logir clear noprompt" % self.controller
        if process.system(cmd, ignore_status=True, shell=True) != 0:
            self.fail("Failed to clear the logs on controller")

    def rebuild(self):

        """
        This functions waits for the rebuild to complete on a Raid
        """
        self.set_online_offline("offline")
        while self.adapter_status("Volume state").strip("\n") != 'Optimal':
            time.sleep(30)

    def set_online_offline(self, state):

        """
        This is a helper function, to change the state of the drives
        """
        cmd = "./sas3ircu %d set%s %s" \
              % (self.controller, state, self.disk[0])
        if process.system(cmd, ignore_status=True, shell=True) != 0:
            self.fail("Failed to set drive to %s" % state)

    def adapter_status(self, var):

        """
        This is a helper function, to check the status of the adapter
        """
        cmd = "./sas3ircu %d status" % self.controller
        output = process.run(cmd, shell=True, ignore_status=True)
        if output.exit_status != 0:
            self.fail("Failed to display the status of the adapter")
        for i in output.stdout.splitlines():
            if var in i:
                return i.split(":")[-1].strip(" ").strip("\n")

    def deleteraid(self):

        """
        This function deletes raid array
        """
        cmd = "echo -e 'YES\nNO' | ./sas3ircu %d deletevolume %d" \
              % (self.controller, self.volumeid())
        if process.system(cmd, ignore_status=True, shell=True) != 0:
            self.fail("Failed to delete raid array VR1")

    def volumeid(self):

        """
        This function returns volume ID of the IR volume
        """
        cmd = "./sas3ircu %d display | grep 'vr1' -B 2 | grep 'Volume ID' | \
               awk '{print $4}'" % self.controller
        volume_id = int(process.system_output(cmd, shell=True))
        return volume_id

    def sleepfunction(self):

        """
        This function waits, till the current operation is complete
        """
        while self.adapter_status("Current operation") != 'None':
            time.sleep(10)


if __name__ == "__main__":
    main()
