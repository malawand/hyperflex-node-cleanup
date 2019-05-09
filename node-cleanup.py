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

import sys

import click


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


import os
import sys                                                                                                            
import subprocess
import re            
import getpass  
import string

network_info = {}
vSwitches = ['vswitch-hx-storage-data', 'vswitch-hx-vm-network']
get_vlans_for_networks = ['Storage Controller Management Network', 'Storage Hypervisor Data Network', 'Storage Controller Data Network']
get_vmk_ip = ['Management Network (vmk0)', 'Storage Hypervisor Data Network (vmk1)']
vmk_port_mapping = {
    'Management Network':'vmk0',
    'Storage Hypervisor Data Network':'vmk1'
    }
vSwitch_to_vnic = vSwitches[:]
vmnic_mapping = {}
configured_vmnics = []
portgroup_mapping = {
"Storage Controller Management Network" : "vswitch-hx-inband-mgmt", 
"Storage Controller Replication Network" : "vswitch-hx-inband-mgmt", 
"Storage Hypervisor Data Network" : "vswitch-hx-storage-data",
"Storage Controller Data Network" : "vswitch-hx-storage-data"
}
vlan_mapping = {}



def getPythonVersion():
    print("Checking version of Python")
    if sys.version_info[0] == 3:
        python_version = 3
        return 3
    elif sys.version_info[0] == 2:
        python_version = 2
        return 2
    else:
        print("Unable to determine Python version.")
        print("This script supports Python 2 and 3.")
        sys.exit("Please make sure python is installed on this ESX host. Run the command 'python -V'.")
python_version = getPythonVersion()        
def get_network_info():
    ############################################## DVS Configuration #############################################
    
    ########## Checking for DVS ###########
    print("Are there a DVS's being used for vmotion? (Input 1 for yes and 0 for no)")
    contains_dvs = input()
    if contains_dvs == '1':
        print('This script will not configure for DVS.')
        print('By default, the Management Network port group is created under vswitch-hx-inband-mgmt (unless using vSwitch0).')
        print('This script will not configure DVS settings for Management network. Nor will it remove the Management Network.')
        print('Proceeding.. We will not configure the standard switch for VMotion')
        contains_dvs = True
    else:
        contains_dvs = False

    if contains_dvs is True:
        # Proceed with the current vSwitches, get_vlans_for_networks, and get_vmk_ip
        print('\n')
    else:
        vmotion_vswitch_name = 'vmotion'
        vSwitches.append('vmotion')
        get_vlans_for_networks.append('vmotion')
        get_vmk_ip.append('vmotion (vmk2)')
        set_vmk_port_mapping('vmotion','vmk2')
        setPortGroupMapping('vmotion', 'vmotion')
        set_vmnic_mapping('vmnic6', vmotion_vswitch_name)
        set_vmnic_mapping('vmnic7', vmotion_vswitch_name)
                
	############################################## End DVS Configuration #############################################
	
    ############################################# ISCSI Configuration #############################################
    print('Do you have ISCSI configured in the network? (Input 1 for yes and 0 for no)')
    contains_iscsi = input()
    if contains_iscsi == '1':
        # Add ISCSI vswitch to the list of switches to be configured.
        vSwitches.append('vswitch-hx-iscsi')
        # How many network paths?
        # Some companies have two networks configured for each network path. 
        # If they have two network paths, 
            # vmk3 will be used for the first network path 
            # vmk4 will be used for the second network path
        # If they have one network path
            # vmk3 will be used for ISCSI 
        print("How many network paths? (Input 1 or 2 for options below)")
        print('1. One network path \n2. Two network paths')
        iscsi_paths = input()
        if iscsi_paths == '1':
            # Add vmk3 for iscsi
            print('ISCSI will be configured on vmk3 (iscsi)')
            get_vlans_for_networks.append('iscsi')
            get_vmk_ip.append('iscsi (vmk3)')
            set_vmk_port_mapping('iscsi', 'vmk3')
            setPortGroupMapping('iscsi', 'vswitch-hx-iscsi')
        elif iscsi_paths == '2':
            print('ISCSI will be configured on vmk3 (iscsi-a for path 1) and vmk4 (iscsi-b for path 2)')
            get_vlans_for_networks.append('iscsi-a')
            get_vlans_for_networks.append('iscsi-b')
            get_vmk_ip.append('iscsi-a (vmk3)')
            set_vmk_port_mapping('iscsi-a', 'vmk3')
            get_vmk_ip.append('iscsi-b (vmk4)')
            set_vmk_port_mapping('iscsi-b', 'vmk4')
            setPortGroupMapping('iscsi-a', 'vswitch-hx-iscsi')
            setPortGroupMapping('iscsi-b', 'vswitch-hx-iscsi')

    ######################################### End ISCSI Configuration #############################################
    ######################################### VLANs to be Configured #############################################
    print('\n\n')
    print('VLANs to be configured:')
    for i in get_vlans_for_networks:
        print('     ' + i)
    print ('\n')
    print("VMK's to be configured:")
    for vmk in get_vmk_ip:
        print('     ' + vmk)
        network_info[str(vmk)] = {''}

    print('\n')
    print('VSwitches to be configured:')
    for i in vSwitches:
        print('     ' + i)
    
    print('\n')
    for network in get_vlans_for_networks:        
        if python_version == 2:
            network_info[network] = raw_input("What is the VLAN # for "+network+"?\n")
            while not validateInts(network_info[network]):
                print('     The VLAN you input is invalid. Please input a valid VLAN')
                network_info[network] = raw_input("What is the VLAN # for "+network+"?\n")
        elif python_version == 3:
            print("What is the VLAN # for "+network+"?")
            network_info[network] = input()
            while not validateInts(network_info[network]):
                print('     The VLAN you input is invalid. Please input a valid VLAN')
                network_info[network] = input()
        setVlanMapping(network, network_info[network])
        
    for vmk in get_vmk_ip:
        if(python_version == 2):
            print("VMK: " + vmk)
            vmk_network_info1 = raw_input("What is the IP address for " + vmk + "? ")            
            while not validateIP(vmk_network_info1):
                print(vmk_network_info1 + " is a invalid IP address. Please try again.")
                vmk_network_info1 = raw_input("What is the IP address for " + vmk + "? ")
            network_info[vmk] = str(vmk_network_info1)


            netmask = raw_input("What is the netmask?")
            while not validateIP(netmask):
                print(netmask + " is a invalid IP address. Please try again")
                netmask = raw_input("What is the netmask? ")
            network_info[(vmk+' - Netmask')] = netmask

            gw = raw_input("What is the gateway? Input 0.0.0.0 if no G/W")
            while not validateIP(gw):
                print(gw + ' is not a valid IP address. Please try again')
                gw = raw_input("What is the gateway? ")
            network_info[(vmk+' - Gateway')] = gw
            # network_info[(vmk+' - Gateway')] = str(network_info[(vmk+' - Gateway')])
        elif(python_version == 3):
            print("What is the IP address for " + vmk + "?")
            ip = input()
            while not validateIP(ip):
                print(ip + ' is an invalid IP. Please try again.')
                ip = input()
            network_info[vmk] = ip
            
            print("What is the netmask?")
            nm = input()
            while not validateIP(nm):
                print(nm + ' is an invalid IP. Please try again')
                nm = input()
            network_info[(vmk+' - Netmask')] = nm
            
            print("What is the gateway? Input 0.0.0.0 if no G/W")
            gw = input()
            while not validateIP(gw):
                print(gw + ' is an invalid IP. Please try again.')
                gw = input()
            network_info[(vmk+' - Gateway')] = gw
        
    ##########################
    #  Print Network Config  #
    ##########################

    print('------- Configuration -------')
    print('\n')
    print('VLANS: ')    
    for i in get_vlans_for_networks:
        print('     ' + str(i) + ': ' + str(network_info[i]))
        # print('     ', i, ': ', network_info[i])
    print(' ')    
    print("VMK's: ")
    if python_version == 2:
        print("In python == 2")
        for vmk in get_vmk_ip:
            print("VMK: " + vmk)
            print('')
            vmk = str(vmk)            
            vmk_value = network_info[vmk]
            vmk_value = str(vmk_value)
            print("     " + vmk + ": " + vmk_value)

            vmk_netmask = vmk + " - Netmask"
            vmk_netmask = str(vmk_netmask)
            vmk_value_netmask = network_info[vmk_netmask]
            vmk_value_netmask = str(vmk_value_netmask)
            print("     " + vmk + ": " + vmk_value_netmask)

            vmk_gateway = vmk + " - Gateway"
            vmk_gateway = str(vmk_gateway)
            vmk_value_gateway = network_info[vmk_gateway]
            vmk_value_gateway = str(vmk_value_gateway)
            print("     " + vmk + ": " + vmk_value_gateway)

    
    elif python_version == 3:
        for vmk in get_vmk_ip:
            print('     ', vmk, ': ', network_info[vmk])
            print('     ', vmk, ': ', network_info[vmk + ' - Netmask'])
            print('     ', vmk, ': ', network_info[vmk + ' - Gateway'])
            print(' ')               

    
    print(' ')
    print('vSwitches: ')
    if python_version == 2:
        for vswitch in vSwitches:
            print("     " + vswitch)
    elif python_version == 3:
        for vswitch in vSwitches:
            print('     ', vswitch)
    print('\n')
    print('----- End Configuration -----')

def validateIP(ip):
    return bool(re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$",ip))

def validateInts(input):
    return bool(re.match('^[0-9]+$', input))

def get_inband_mgmt_vswitch():
	# Confirm that vswitch-hx-inband-mgmt is available
	print("checking for vswitch-hx-inband-mgmt switch")
	cmd = "esxcli network vswitch standard list | grep -i 'vswitch-hx-inband-mgmt'"
	output = os.popen(cmd).readlines()
	if("Name: vswitch-hx-inband-mgmt" in str(output)):
		print("vswitch-hx-inband-mgmt exists.. Proceeding")
		return 'vswitch-hx-inband-mgmt'
	else:
		print('vswitch-hx-inband-mgmt does not exist.. Checking for vmk0')
		cmd = "esxcli network ip interface list | grep -i vmk0 -A 4"
		output = os.popen(cmd).readlines()
		for line in output:
			if re.match("(.*)(P|p)ortset:(.*)", line):
				r1 = re.findall(r"(?<=:\s)[\w-]+", line)
				mgmt_vswitch = r1[0]
				print(mgmt_vswitch) 
				# Check if vSwitch0
				if mgmt_vswitch != 'vswitch-hx-inband-mgmt':
					print("The switch attached to vmk0 is not named vswitch-hx-inband-mgmt. We highly recommend renaming " + mgmt_vswitch + " to vswitch-hx-inband-mgmt. TAC recommends you stop here and rename the vswitch, then re-run this script.\n Would you like to proceed anyways by adding the necessary port groups to " + mgmt_vswitch + "? (Select from the options below). ")
					print('\n 1. Yes\n 2. No, I would like to rename ' +mgmt_vswitch+ ' to vswitch-hx-inband-mgmt')
					option = input()
					if option == '1':
                        			editInbandMgmtPortGroupMapping(mgmt_vswitch)
                        			set_vmnic_mapping('vmnic1', mgmt_vswitch)
                        			return mgmt_vswitch
					elif option == '2':
						sys.exit("VMK0 is on "+mgmt_vswitch+". We need to rename "+mgmt_vswitch+" to vswitch-hx-inband-mgmt. \nPlease delete "+mgmt_vswitch+" and rename it to vswitch-hx-inband-mgmt and run this script again.")
			else:
				set_vmnic_mapping('vmnic1','vswitch-hx-inband-mgmt')
				return 'vswitch-hx-inband-mgmt'
def createvSwitches():
	# Adding the basic vSwitches	
	for vSwitch in vSwitches:
		print('Adding vSwitch: ' + vSwitch)
		cmd = "esxcli network vswitch standard add -v " + vSwitch
		output = os.popen(cmd).readlines()
		if "A portset with this name already exists" in str(output):
			print('vSwitch ' + vSwitch + " already exists.. Moving on to the next switch")
		if str(output) == "[]":
			print(vSwitch + " added")

def enableJumboFrames():
    for vswitch in vSwitches:
        print('Enabling Jumbo frames for vswitch: ' + vswitch)
        os.system('esxcli network vswitch standard set -m 9000 -v ' + vswitch)

def set_vmnic_mapping(vmnic, vswitch):
    vmnic_mapping[vmnic] = vswitch
    configured_vmnics.append(vmnic)

def get_vmnic_mapping():
    return vmnic_mapping

def get_vmnic_mapping_by_key(vmnic):
    return vmnic_mapping.get(vmnic)

def addVmnics(inband_mgmt_vswitch):
    
    vSwitch_to_vnic.insert(0, inband_mgmt_vswitch)
    
    vmnic = 1
    vswitch_index = 0

    for vswitch in vSwitch_to_vnic:
        print('vswitch: ' + vswitch)
        if vswitch_index == 0:
            command = 'esxcli network vswitch standard uplink add -u vmnic' + str(vmnic) + ' -v ' + str(vSwitch_to_vnic[vswitch_index])
            set_vmnic_mapping('vmnic' + str(vmnic), vSwitch_to_vnic[vswitch_index])
            vswitch_index += 1
            # vmnic +=1
            os.system(command)
        elif vswitch_index != 0 and vmnic != 0: 
            print('vswitch: ' + vswitch)
            vmnic += 1
            print('Setting vmnic' + str(vmnic) + ' to ' + vSwitch_to_vnic[vswitch_index])
            command = 'esxcli network vswitch standard uplink add -u vmnic' + str(vmnic) + ' -v ' + str(vSwitch_to_vnic[vswitch_index])
            set_vmnic_mapping('vmnic' + str(vmnic), vSwitch_to_vnic[vswitch_index])            
            os.system(command)

            print('Setting vmnic' + str(vmnic) + ' to ' + vSwitch_to_vnic[vswitch_index])
            vmnic += 1
            command = 'esxcli network vswitch standard uplink add -u vmnic' + str(vmnic) + ' -v ' + str(vSwitch_to_vnic[vswitch_index])
            set_vmnic_mapping('vmnic' + str(vmnic), vSwitch_to_vnic[vswitch_index])            
            os.system(command)

            vswitch_index += 1
            

def vmnicsToActiveStandby():

    print(get_vmnic_mapping())

    print(configured_vmnics)
    configured_vmnics.insert(0,'vmnic0')
    counter = 0
    previous_vmnic = ''
    command = ''
    for vmnic in configured_vmnics:
        if counter <= len(configured_vmnics):
            if counter % 2 == 1:
                if(counter == 1):
                    vmnic_mapping = 'vswitch-hx-inband-mgmt'
                    print("esxcli network vswitch standard policy failover set -a vmnic" + str(counter-1) + ' -s vmnic' + str(counter) + ' -v ' + vmnic_mapping)
                    command = "esxcli network vswitch standard policy failover set -a vmnic" + str(counter-1) + ' -s vmnic' + str(counter) + ' -v ' + vmnic_mapping
                    # print("esxcli network vswitch standard policy failover set -a " + previous_vmnic + ' -s ' + vmnic + ' -v ' + vmnic_mapping)
                    # command = "esxcli network vswitch standard policy failover set -a " + str(previous_vmnic) + ' -s ' + str(vmnic) + ' -v ' + vmnic_mapping
                elif(counter == 5):
                    vmnic_mapping = 'vswitch-hx-vm-network'
                    print('esxcli network vswitch standard policy failover set -a vmnic' + str(counter-1) + ',vmnic' + str(counter) + ' -v ' + vmnic_mapping)
                    command = 'esxcli network vswitch standard policy failover set -a vmnic' + str(counter-1) + ',vmnic' + str(counter) + ' -v ' + vmnic_mapping
                    # print('esxcli network vswitch standard policy failover set -a ' + previous_vmnic + ',' + vmnic + ' -v ' + vmnic_mapping)
                    # command = 'esxcli network vswitch standard policy failover set -a ' + str(previous_vmnic) + ',' + str(vmnic) + ' -v ' + vmnic_mapping
                elif(counter == 7):
                    vmnic_mapping = 'vmotion'
                    print("esxcli network vswitch standard policy failover set -a vmnic" + str(counter-1) + ' -s vmnic' + str(counter) + ' -v ' + vmnic_mapping)
                    command = "esxcli network vswitch standard policy failover set -a vmnic" + str(counter-1) + ' -s vmnic' + str(counter) + ' -v ' + vmnic_mapping
                    # print("esxcli network vswitch standard policy failover set -a " + previous_vmnic + ' -s ' + vmnic + ' -v ' + get_vmnic_mapping_by_key(vmnic))
                    # command = "esxcli network vswitch standard policy failover set -a " + str(previous_vmnic) + ' -s ' + str(vmnic) + ' -v ' + get_vmnic_mapping_by_key(vmnic)
                elif(counter == 3):
                    vmnic_mapping = 'vswitch-hx-storage-data'
                    print("esxcli network vswitch standard policy failover set -s vmnic" + str(counter-1) + ' -a vmnic' + str(counter) + ' -v ' + vmnic_mapping)
                    command = "esxcli network vswitch standard policy failover set -a vmnic" + str(counter-1) + ' -s vmnic' + str(counter) + ' -v ' + vmnic_mapping
                os.system(command)
                counter +=1
            else:
                previous_vmnic = str(vmnic)
                counter += 1
        else:
            print("counter is bigger than the size of configured vmnic")


def createPortGroups():
    port_groups = getPortGroupMapping()

    for value in port_groups:
        print("Creating " + value + " port group on " + port_groups[value])
        command = 'esxcli network vswitch standard portgroup add -p "' + value + '" -v ' + port_groups[value]
        os.system(command)



def setVLANS():
    vlans = getVlanMapping()

    for portgroup in vlans:
        print('Setting portgroup ' + str(portgroup) + ' to VLAN ' + str(vlans[portgroup]))
        # print('esxcli network vswitch standard portgroup set -p "' + portgroup + '" -v '+ vlans[portgroup] )
        command = 'esxcli network vswitch standard portgroup set -p "' + str(portgroup) + '" -v '+ str(vlans[portgroup])
        os.system(command)

def createVMKernelPorts():
    vmkports = get_vmk_port_mapping()

    for vmkPortName in vmkports:
        if vmkPortName == 'Management Network':
            print("Skipping configuration of vmk0.. not needed.")
        else:
            command = 'esxcli network ip interface add -i ' + str(vmkports[vmkPortName]) + ' -p ' + '"' + str(vmkPortName) + '" -m 9000'
            print(command)
            os.system(command)
            output = os.popen(command).readlines()                  
        # os.system('esxcli network ip interface add -i ' + vmkports[vmkPortName] + ' -p ' + '"' + vmkPortName + '" -m 9000')
        # print('esxcli network ip interface add -i ' + vmkports[vmkPortName] + ' -p ' + '"' + vmkPortName + '" -m 9000')


def assignIpToVmkernel():
    counter = 0
    print("In assign vmkernel to ip")

    if python_version == 2:
        for vmk in get_vmk_ip:
            command = 'esxcli network ip interface ipv4 set -i vmk' + str(counter) + ' -I ' + network_info[vmk] + ' -N ' + network_info[vmk + ' - Netmask'] + ' -t static '
            print(command + '\n')
            os.system(command)
            counter+=1
    elif python_version == 3:
        for vmk in get_vmk_ip:
            command = 'esxcli network ip interface ipv4 set -i vmk' + str(counter) + ' -I ' + network_info[vmk] + ' -N ' + network_info[vmk + ' - Netmask'] + ' -g ' + network_info[vmk + ' - Gateway'] + ' -t static '
            print(command)
            os.system(command)
            # print('esxcli network ip interface ipv4 set -i vmk' + str(counter) + ' -I ' + network_info[vmk] + ' -N ' + network_info[vmk + ' - Netmask'] + ' -g ' + network_info[vmk + ' - Gateway'] + ' -t static ')
            counter+=1

def editInbandMgmtPortGroupMapping(inband_mgmt_vswitch):
    portgroup_mapping["Storage Controller Management Network"] = inband_mgmt_vswitch
    portgroup_mapping["Storage Controller Replication Network"] = inband_mgmt_vswitch

def setPortGroupMapping(key, value):
    portgroup_mapping[key] = value

def getPortGroupMapping():
    return portgroup_mapping

def setVlanMapping(network, vlan):
    vlan_mapping[network] = vlan

def getVlanMapping():
    return vlan_mapping

def set_vmk_port_mapping(vmk_port_name, vmk):
    vmk_port_mapping[vmk_port_name] = vmk

def get_vmk_port_mapping():
    return vmk_port_mapping
    
def main():	
	####################################
	#	   Gathering Network Data	   #
	####################################
    if(getPythonVersion() == 2):
        print("Executing python2 functions")
    elif(getPythonVersion() == 3):
        print("Executing python3 functions")
    inband_mgmt_vswitch = get_inband_mgmt_vswitch()
#    set_vmnic_mapping('vmnic1', inband_mgmt_vswitch)
    get_network_info()
    createvSwitches()
    addVmnics(inband_mgmt_vswitch)    
    createPortGroups()
    setVLANS()
    createVMKernelPorts()
    assignIpToVmkernel()
    vmnicsToActiveStandby()
    enableJumboFrames()

if __name__ == "__main__":
    main()
