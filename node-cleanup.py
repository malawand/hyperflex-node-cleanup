#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""hyperflex-node-cleanup Console Script.
Copyright (c) 2019 Cisco and/or its affiliates.
This software is licensed to you under the terms of the Cisco Sample
Code License, Version 1.1 (the "License"). You may obtain a copy of the
License at
               https://developer.cisco.com/docs/licenses
All use of the material herein must be in accordance with the terms of
the License. All rights not expressly granted by the License are
reserved. Unless required by applicable law or agreed to separately in
writing, software distributed under the License is distributed on an "AS
IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
or implied.
"""

__author__ = "Mazen Lawand"
__email__ = "malawand@cisco.com"
__version__ = "0.1.0"
__copyright__ = "Copyright (c) 2019 Cisco and/or its affiliates."
__license__ = "Cisco Sample Code License, Version 1.1"

#  This script restores the networking settings for a storage controller virtual machine on a HyperFlex ESXi host.
# The script should be used if:
#   1. ESXi was re-imaged on a 240 M5 or M4 HCS HX Node
#   2. Something or someone accidentally changed the ESXi host network settings and it needs to be restored.
#
# How to use:
#   1. Put the script on the affected host via FTP/SCP
#   2. Run the command, 'py esxi-restore.py'
#   3. Input all of the IP addresses that is requested for that host
################################################################################################
#   This script is used to clean up an existing HyperFlex node running ESXi.                   #
#   This script is NOT used to cleanup the cluster itself, but just the node in the cluster    #
#   If you need to clean the cluster, run the destroy cluster command on                       #
#   the CMIP and run this script on every ESXi host to properly clean it up                    #
#                                                                                              #
#   Put this script on a non-HX datastore directory under /vmfs/volumes                        #
#   Example: /vmfs/volumes/23e5b079-c8e4b237-766d-0a8c460c9dac/                                #
#   /vmfs/volumes/23e5b079-c8e4b237-766d-0a8c460c9dac/hx-clean.py                              #
#   cd /vmfs/volumes/23e5b079-c8e4b237-766d-0a8c460c9dac/                                      #
#   Run the python script: python hx-clean.py                                                  #
#                                                                                              #
#   If there are errors, read the errors and delete what this script is attempting to delete   #
#   and run the script again as many times as needed until the node is completely cleaned      #
################################################################################################

import os
import sys
import subprocess
import re
import getpass
import string
import time
from itertools import islice
import json
from pprint import pprint


def getPythonVersion():
    # print("Checking version info....")
    print(sys.version_info[0])

def relinquishSCVM():
    if(getPythonVersion() == 2):
        # Python 2 function
        print("Python 2 command")
    elif(getPythonVersion() == 3):
        # Python 3 function
        print("Python 3 command")

def sshIntoSCVM():    
    # Getting IP address of the Storage Controller VM
    # command = '/opt/springpath/support/getstctlvmip.sh "Storage Controller Management Network"'
    # output = executeFunctionWithReadlines(command)
    # output = os.popen('/opt/springpath/support/getstctlvmip.sh "Storage Controller Management Network"').readlines()
    # output = re.finditer(r'[0-9.]',str(output), re.MULTILINE)
    # ip = ''
    # for matchNum, match in enumerate(output):        
    #     ip += match.group()
    
    # Check for VM's other than the storage controller VM on the node.
    # executeFunction(command)

    command = "vim-cmd vmsvc/getallvms | sed -n '1!p' | wc -l"
    numberOfLines = int(executeFunctionWithRead(command))

    command = "vim-cmd vmsvc/getallvms | sed -n '1!p'"
    vm_list = executeFunctionWithRead(command)
    # Validating only 1 vm exists on the host, the SCVM
    if numberOfLines == 1:
        vm_list = vm_list.split(" ")
        vm_id = vm_list[0]
        vm_name = vm_list[6]        
        # Check to see if the VM is powered off    
        command = 'vim-cmd vmsvc/power.get ' + vm_id + " | sed -n '1!p'"
        power_state = executeFunctionWithRead(command)        
        power_state = str(power_state.split(" ")[1].strip())
        
        
        if power_state == "on":
            print("Has the SCVM been relinquished? Input 1 for yes and 0 for no")
            scvm_relinquished = input()
            if scvm_relinquished == "1":            
                powerOffSCVM(vm_id)
            elif scvm_relinquished == "0":
                print("Please relinquish the SCVM from the cluster before proceeding.")
                print("SSH into the storage controller VM as root. ssh root@" + ip)
                print("Issue the command: python /usr/share/springpath/storfs-misc/relinquish_node.py ")
        elif power_state == "off":
            print("SCVM is powered off")
            destroySCVM(vm_id)
    elif(numberOfLines == 0):
        print("There are no SCVM's.. Proceeding to deleting networking")
        deletePortGroups()
    else:
        print("Please migrate all of the VM's off of the node before continuing. Do not migrate the SCVM")
        
    
def powerOffSCVM(vm_id):
    vm_id = vm_id
    print("powering off SCVM ...")
    command = 'vim-cmd vmsvc/power.off ' + str(vm_id)
    result = executeFunctionWithRead(command)    
    
    command = "vim-cmd vmsvc/power.get " + str(vm_id) + " | sed -n '1!p'"
    result = str(executeFunctionWithRead(command)).split(" ")[1].strip()
    if result == "off":
        print("SCVM is off")
        destroySCVM(vm_id)
    else: 
        print("There was a problem powering down the SCVM. Please make sure it's powered off and run this script again.")
    
def destroySCVM(vm_id):
    print("Destroying the SCVM")
    command = 'vim-cmd vmsvc/destroy ' + str(vm_id)
    result = executeFunctionWithReadlines(command)
    if len(result) == 0:
        print("SCVM has been destroyed. Proceeding to clean up the networking")
        deletePortGroups()
    elif(len(result) > 0 and 'vim.fault.NotFound' in result[0]):
        print("The vm doesnt exist.. Proceeding to clean up the networking")
        deletePortGroups()

portgroup_list = []
def deletePortGroups():
    command = "esxcli network vswitch standard portgroup list | sed -n '2!p' | sed -n '1!p'"
    result = executeFunctionWithReadlines(command)    
    listCounter = 0
    for line in result:
        line = line.split("  ")
        listCounter = listCounter + 1        
        counter = 0
        vswitch_port_group_list = {}
        for index in line:            
            if (index is not ''):
                counter = counter + 1
                if counter == 1:
                    vswitch_port_group_list["name"] = index.strip()
                if counter == 2:
                    vswitch_port_group_list["Virtual Switch"] = index.strip()
                if counter == 3:
                    vswitch_port_group_list["Active Clients"] = index.strip()
                if counter == 4: 
                    vswitch_port_group_list["VLAN ID"] = index.strip()
        portgroup_list.insert(listCounter, vswitch_port_group_list)
    for index in portgroup_list:
        if(index["name"] == "Management Network"):
            print("Skipping deletion of " + index["name"])
        else:
            command = 'esxcli network vswitch standard portgroup remove -v '+index['Virtual Switch']+' -p "'+index['name']+'"'
            output = executeFunctionWithReadlines(command)
            print(output)
    
    command = "esxcli network vswitch standard portgroup list | sed -n '2!p' | sed -n '1!p' | wc -l" 
    result = executeFunctionWithRead(command)
    result = str(result).strip()    
    print("Length of port group list: " + str(result))
    if int(result) == 2 or int(result) == 1:
        print("All necessary port groups have been deleted.. Moving on to delete the VMK's")
        deleteVMKs()        
    else:
        print("There was a problem with deleting the port groups from the vswitches. Please delete the port groups from the vswitches and try again.")

    
def deleteVMKs():
    print("Deleting VMKernel Adapters")
    
    command = 'esxcli network ip interface list | grep "Name: vmk*"'
    result = executeFunctionWithReadlines(command)
    for line in result:
        line = line.split(" ")
        for index in line:
            if index != '':
                if "vmk" in str(index):
                    index = str(index).strip()
                    print("index: " + index[3])
                    if int(index[3]) >= 1:
                        command = "esxcli network ip interface remove -i " + index
                        output = executeFunctionWithReadlines(command)
                        verification_command = 'esxcli network ip interface list | grep "Name: vmk*" | wc -l'
                        result = executeFunctionWithRead(verification_command)  
                        result = str(result).strip()
                        if int(result) == 1:                    
                            print("All necessary VMK's have been deleted. Proceeding with deleting vswitches...")
                            deleteVswitches(portgroup_list)
                        else:
                            print("There was a problem with deleting the necessary VMK's. Please delete all the VMK's except vmk0 and run this script again.")
                    else:
                        if(int(executeFunctionWithRead("esxcli network ip interface list | grep -i 'Name: vmk*' | wc -l")) == 1):
                            print("Only vmk0 exists.. proceeding to delete vswitches")
                            deleteVswitches(portgroup_list)

def deleteVswitches(portgroup_list):
    print("Deleting the vswitches")
    
    command = 'esxcli network vswitch standard list | grep "Name: "'
    result = executeFunctionWithReadlines(command)
    vswitches = []
    # Getting the vswitches to delete
    for line in result:
        line = line.split(" ")        
        for index in line:
            if index is not '' and 'Name:' not in index:
                vswitches.append(str(index).strip())        

    for vswitch in vswitches:
        if "vswitch-hx-inband-mgmt" in vswitch:
            print("Not deleting: " + str(vswitch) + '. Moving on..')
        else:
            command = 'esxcli network vswitch standard remove -v "'+vswitch+'"'
            output = executeFunctionWithRead(command)

    # Verify that vswitches have been deleted
    verification_command = 'esxcli network vswitch standard list | grep -i Name | wc -l'
    result = executeFunctionWithRead(verification_command)
    result = str(result).strip()
    if int(result) == 1:
        print("All vswitches have been deleted. Proceed to delete orphaned SCVM")
        deleteOrphanedSCVM()
    else:
        print("There was a problem with deleting the vswitches. Please delete all of the vswitches EXCEPT vswitch-hx-inband-mgmt and run this script again. ")

def deleteOrphanedSCVM():
    print("Please delete the orphaned SCVM from VCenter... Press 1 when this has been complete")
    deletedOrphanVm = input()
    if int(deletedOrphanVm) == 1:
        deleteDataStores()
    else:
        print("Please remove the orphaned VM and run this script again")

listOfDataStores = []
setOfDataStores = {}
def deleteDataStores():
    print("Starting datastore deletion")
    command = "grep -i nas /etc/vmware/esx.conf"
    result = executeFunctionWithReadlines(command)
    # output = os.popen(command)
    # result = output.readlines()
    for line in result:
        if "STFSNasPlugin" in line:
            print("Not deleting " + line)
        else:
            line = line.split("/")
            # print(line[2])
            listOfDataStores.append(str(line[2]))
    setOfDataStores = set(listOfDataStores)
    
    if len(setOfDataStores) >= 1:
        for ds in setOfDataStores:
            command = "esxcfg-nas -d " + ds
            print("Deleting datastore: " + ds + ". This may take a moment")
            print(command)
            output = executeFunctionWithRead(command)
            print(output)
    verification_command = "grep -i nas /etc/vmware/esx.conf | wc -l"
    numberOfDatastores = int(executeFunctionWithRead(verification_command))
    print("The length of the datastores: " + str(numberOfDatastores))
    if numberOfDatastores == 2:
        print("All necessary datastores have been deleted. Proceeding to SSD cleaning.")        
        uninstallESXIVibs()
        # cleanInternalSSD()
    else:
        print("Something went wrong while deleting the datastores. Please delete the datastores and run this script again.")

filesystem_list = []
set_of_commands = []
def cleanInternalSSD():
    counter = 0
    command = 'esxcli storage filesystem list'
    result = executeFunctionWithReadlines(command)
    # output = os.popen(command)
    # result = output.readlines()
    uuid = ''
    for line in result:
        # print(line)
        if('SpringpathDS' in line):
            line = line.split(" ")
            for index in line:
                if index is not '':
                    counter = counter+1
                    filesystem_list.insert(counter, index)
            uuid = filesystem_list[2]
            print(uuid)
    command2 = 'esxcli system coredump file remove --force'
    executeFunctionWithRead(command2)
    command3 = 'esxcfg-dumppart -d'
    executeFunctionWithRead(command3)
    command4 = 'rm -rf /scratch'
    executeFunctionWithRead(command4)
    command5 = 'ps | grep vmsyslogd'
    result = executeFunctionWithReadlines(command5)
    # output = os.popen(command5)
    # result = output.readlines()
    zibby = []
    zibCount = 0
    for line in result:
        line = line.split(" ")
        for index in line:
            if index is not '':
                zibCount = zibCount + 1
                zibby.insert(zibCount, index)
    process = zibby[1]
    command6 = 'kill -9 ' + str(process)
    executeFunctionWithRead(command6)
    command7 = 'esxcli storage filsystem unmount -p /vmfs/volumes/' + str(uuid)
    executeFunctionWithRead(command7)

    print("Do we need to clean the SSD's? Note: SSD's need to be cleaned IF: \n 1. Node is being added back into a cluster running HyperFlex that is not 3.0+ \n 1. The whole cluster is being redeployed \n Input 1 for yes or 0 for no")
    cleanSSDs = input()
    if(cleanSSDs == "1"):
        # Get the hardware to confirm how we will be cleaning the SSD's
        serverModel = getServerModel()
        print("The server model: " + serverModel)
        if 'M5' in serverModel or 'm5' in serverModel:
            print("This is an M5.. cleaning")
            cleanM2SSDM5()
        elif 'M4' in serverModel or 'm4' in serverModel:
            print("This is an M4.. cleaning")
            cleanBackSSDM4()
        else:
            print("This node does not have an M.2 SSD or back SSD that needs to be cleaned. Moving on..")
    else:
        print("Please reboot the ESXi host and redeploy HX.")


def getServerModel():
    command = 'esxcli hardware platform get | grep -i "product name"'
    # output = os.popen(command)
    # result = output.read()
    result = executeFunctionWithRead(command)
    if str(result).startswith('Product Name:'):
        print(result)
    device_model = ((str(result)).strip()[13:str(result).find('.')]).strip()    
    return device_model

partitionList = []
def cleanM2SSDM5():
    # result = getM4BackSSDPartitionList()
    print("Skipping SSD cleaning on this M5")

    # for listItem in result:
        # print(listItem)
        # if ((int(listItem[1]) == 0) or (int(listItem[1]) == 3)):
        #     print("Skipping partition " + listItem[1])
        # else:
        #     command = 'partedUtil delete /vmfs/devices/disks/' + str(listItem[0]) + ' ' + str(listItem[1])
        #     print("The partedutil Command: ")
        #     print(command)
            # executeFunctionWithReadlines(command)
    # uninstallESXIVibs()
    
    # print(result)
    
    # output = os.popen(command)
    # result = output.read()
    # if str(result).startswith('Product Name:'):
    #     print(result)
    # device_model = (str(result)).strip()[13:str(result).find('.')]
    # print(device_model.strip())

def getM4BackSSDPartitionList():
    m4PartitionList = []
    print("in getM4BackSSDPartitionList")
    command = "esxcli storage core device partition list | sed -n '2!p' | sed -n '1!p'"
    # output = os.popen(command)
    # result = output.readlines()
    result = executeFunctionWithReadlines(command)
    partitionIndex = 0
    temp = []
    for line in result:       
        # print(line)        
        if 't10' in line:            
            partitionIndex = partitionIndex + 1
            line = line.split(" ")
            temp = []
            for index in line:
                if index is not '':
                    temp.append(index)            
            m4PartitionList.insert(partitionIndex, temp)
    return m4PartitionList
        # print(line)
    

def cleanBackSSDM4():
    print("In cleanBackSSDM4")
    m4PartitionList = getM4BackSSDPartitionList()  
    time.sleep(5)
    for partition in m4PartitionList:                
        if int(partition[1]) == 1:
            command = 'partedUtil delete /vmfs/devices/disks/' + partition[0] + ' ' + partition[1]
            executeFunctionWithReadlines(command)
    
    # Verify that the partition has been deleted, and format SSD to a GPT disk
    partition1Exists = 0
    verifyM4PartitionList = getM4BackSSDPartitionList()

    if len(m4PartitionList) >= 2 and len(m4PartitionList) == 1 and int(m4PartitionList[1]) == 0:
        print("Back SSD on the M4 has successfully been cleaned. \n Ready to proceed to turning disk into gpt. ")
        formatSSDToGPT()        
    elif len(getM4BackSSDPartitionList()) == 1:
        print("Back SSD on the M4 has successfully been cleaned. \n Ready to proceed to turning disk into gpt. ")
        formatSSDToGPT()

def formatSSDToGPT():
    print("In the format SSD to GPT function")
    m4PartitionList = getM4BackSSDPartitionList()    
    command = "partedUtil mklabel /vmfs/devices/disks/" + str(m4PartitionList[0][0]) + " gpt"
    output = executeFunctionWithReadlines(command)
    print(output)
    verification_command = 'partedUtil getpbl /vmfs/devices/disks/' + m4PartitionList[0][0]
    output = executeFunctionWithReadlines(verification_command)
    if len(output) == 0:
        print("Complete. Please reboot the server and redeploy HX. ")        
        # cleanInternalSSD()
        # uninstallESXIVibs()
    # print(verification_command)

def uninstallESXIVibs():
    vibList = []
    print("In the uninstallESXIVibs function")
    command = 'esxcli software vib list | grep -i spring'
    output = executeFunctionWithReadlines(command)
    temp = []
    tempCount = 0
    for line in output:
        temp = []
        tempCount = tempCount + 1
        line = line.split(" ")
        for index in line:    
            if(index is not ''):
                temp.append(index)            
        vibList.insert(tempCount, temp)    
    for vib in vibList:
        command = 'esxcli software vib remove -n ' + vib[0]
        commandOutput = executeFunctionWithReadlines(command)
        # print(commandOutput)
        for response in commandOutput:
            if 'Message' in response and 'successfully' in response:                
                print("Success in removing Vib.. moving on..")
                # print(response)
            elif('Reboot Required' in response and 'true' in response):
                print("ESXi needs to reboot to remove " + vib[0])
                # print(response)
            elif "No VIB matching VIB search specification '" + str(vib) in str(response):
                print("Proceed..")
    cleanInternalSSD()

def executeFunctionWithReadlines(command):
    print("Executing: " + command)
    output = os.popen(command)
    result = output.readlines()
    output.close()
    return result

def executeFunctionWithRead(command):
    print("Executing: " + command)
    output = os.popen(command)
    result = output.read()
    output.close()
    return result
    
def checkSEDStatus():
    print('Is this a SED cluster? Input 1 for yes and 0 for no')
    sed_cluster = input()
    if(sed_cluster == '1'):
        print("Have the disks been unlocked? Input 1 for yes and 0 for no")
        unlocked = input()
        if(unlocked == "1"):
            sshIntoSCVM()
            print("Proceeding.. ")
        else:
            print("Please unlock the drives and run this script again.")
    else:
        print(" This is not a SED clsuter.. Proceeding")
        sshIntoSCVM()
    
    

def main():
    checkSEDStatus()

if __name__ == "__main__":
    main()
