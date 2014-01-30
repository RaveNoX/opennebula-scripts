#!/usr/bin/python

from xml.dom import minidom
from datetime import datetime
import sys, subprocess, json, hashlib

one_vm_bin = 'onevm'
action_command = ['delete', '--recreate']

d_lcm_states = { 'LCM_INIT': 0, 'PROLOG': 1, 'BOOT': 2, 'RUNNING': 3, 'MIGRATE': 4, 'SAVE_STOP': 5, 'SAVE_SUSPEND': 6, 'SAVE_MIGRATE': 7, 'PROLOG_MIGRATE': 8, 'PROLOG_RESUME': 9, 'EPILOG_STOP': 10, 'EPILOG': 11, 'SHUTDOWN': 12, 'CANCEL': 13, 'FAILURE': 14, 'CLEANUP': 15, 'UNKNOWN': 16, 'HOTPLUG': 17 }

# NOTE: in ACTIVE STATE LCM state must be checked
d_states = { 'INIT': 0, 'PENDING': 1, 'HOLD': 2, 'ACTIVE': 3, 'STOPPED': 4, 'SUSPENDED': 5, 'DONE': 6, 'FAILED': 7}

# Make reverce
db_lcm_states = dict((y,x) for x,y in d_lcm_states.items())
db_states = dict((y,x) for x,y in d_states.items())


def jsonDump(obj):
	return json.dumps(obj,sort_keys=True, indent=4)


def getXml():
	global one_vm_bin
	p = subprocess.Popen([one_vm_bin, 'list', '-x'], shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	if p.wait() != 0:
		return None

	return minidom.parse(p.stdout)


def doVmAction(vmid, args):
	global one_vm_bin
	cmd_args = []
	cmd_args.append(one_vm_bin)

	for a in args:
		cmd_args.append(a)

	cmd_args.append(str(vmid))

	p = subprocess.Popen(cmd_args, shell=False, stdout=subprocess.PIPE)
	if p.wait() != 0:
		return False

	return True


def getVms(dom):
	global db_states, db_lcm_states

	vms = []

	for vmn in dom.getElementsByTagName('VM'):
		vm = {}

		for n in vmn.getElementsByTagName('ID'):
			if n.firstChild != None and n.firstChild.nodeValue != None:
				vm['id'] = int(n.firstChild.nodeValue)
				break

		for n in vmn.getElementsByTagName('NAME'):
			if n.firstChild != None and n.firstChild.nodeValue != None:
				vm['name'] = str(n.firstChild.nodeValue)
				break
			

		for n in vmn.getElementsByTagName('STATE'):
			if n.firstChild != None and n.firstChild.nodeValue != None:
				vm['state'] = int(n.firstChild.nodeValue)
				break


		for n in vmn.getElementsByTagName('LCM_STATE'):
			if n.firstChild != None and n.firstChild.nodeValue != None:
				vm['lcm_state'] = int(n.firstChild.nodeValue)
				break

		if 'state' in vm and vm['state'] in db_states:
			vm['state_s'] = db_states[vm['state']]

		if 'lcm_state' in vm and vm['lcm_state'] in db_lcm_states:
			vm['lcm_state_s'] = db_lcm_states[vm['lcm_state']]
			
		
		vms.append(vm)

	return vms


def restartUnknown(vms):
	global d_states, d_lcm_states

	for vm in vms:
		if vm['state_s'] == 'ACTIVE' and vm['lcm_state_s'] == 'UNKNOWN':
			print 'VM "%s-%s" in UNKNOWN state, restarting...' % ( vm['id'], vm['name']  )
			doVmAction(vm['id'], action_command)



def main():
	dom = getXml()

	if dom is None:
		return

	vms = getVms(dom)

	if vms is None:
		return

#	print jsonDump(vms)

	restartUnknown(vms)

	pass


if __name__ == '__main__':
	try:
		ret = main()
		sys.exit(ret)
	except:
		raise

