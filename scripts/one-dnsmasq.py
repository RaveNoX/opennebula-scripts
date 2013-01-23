#!/usr/bin/python

from xml.dom import minidom
from datetime import datetime
import sys, subprocess, json, hashlib, os, socket, struct

file_prefix = 'one-'
file_postfix = '.conf'

dnsmasq_confd = '/etc/dnsmasq/conf.d'
dnsmasq_optd = '/etc/dnsmasq/opts.d'
dnsmasq_hostd = '/etc/dnsmasq/hosts.d'
dnsmasq_bin = '/usr/sbin/dnsmasq'
dnsmasq_restart = 'service dnsmasq restart'
dnsmasq_reload = 'killall -HUP dnsmasq'

one_mac_prefix = '02:00'
one_vnet_bin = 'onevnet'


dhcp_option_map = {}


def getOptionMap():
	global dnsmasq_bin

	p = subprocess.Popen([dnsmasq_bin, '--help', 'dhcp'], shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	if p.wait() != 0:
		return None

	ret = {}

	fl = True
	for l in p.stdout:
		if fl:
			fl = False
			continue

		l = l.strip()
		kv = l.split(' ',2)

		ret[int(kv[0])] = kv[1].lower()

	return ret


def jsonDump(obj):
	return json.dumps(obj,sort_keys=True, indent=4)


def getXml():
	global one_vnet_bin
	p = subprocess.Popen([one_vnet_bin, 'list', '-x'], shell=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
	if p.wait() != 0:
		return None

	return minidom.parse(p.stdout)

def updateVnet(ret):
	if ret is None:
		return None

	needFields = ['id','name','bridge','template', 'type', 'range']

	for f in needFields:
		if not f in ret:
			return None
	
	if ret['type'] == 1:	
		# fixed range
		return None
	else:
		del ret['type']

	if 'vlan' in ret:
		if ret['vlan'] != 0:
			return None
		else:
			del ret['vlan']

	tpl = ret['template']

	if not ('dhcp-enable' in tpl and tpl['dhcp-enable'] in ['1', 'yes'] ):
		return None
	else:
		del tpl['dhcp-enable']

	if 'mask' in tpl and not 'network-mask' in tpl:
		tpl['network-mask'] = tpl['mask']
		del tpl['mask']

	if not 'network-mask' in tpl:
		return None
	else:
		ret['netmask'] = tpl['network-mask']
		del tpl['network-mask']

	if 'broadcast' in tpl:
		ret['broadcast'] = tpl['broadcast']
		del tpl['broadcast']

	if 'dhcp-lease-time' in tpl:
		ret['lease-time'] = tpl['dhcp-lease-time']
		del tpl['dhcp-lease-time']

	rng = ret['range']

	if 'start' in rng and 'end' in rng:
		return ret


	return None


def procVnet(vnet):
	ret = {}

	nodes = {'name':'NAME', 'dev': 'PHYDEV', 'bridge': 'BRIDGE'}
	inodes = {'id': 'ID', 'vlan': 'VLAN', 'type':'TYPE'}


	for k,v in nodes.items():
		for n in vnet.getElementsByTagName(v):			
			if n.firstChild != None and  n.firstChild.nodeValue != None:
				ret[k] = n.firstChild.nodeValue
				break		
	
	for k,v in inodes.items():
		for n in vnet.getElementsByTagName(v):			
			if n.firstChild != None and  n.firstChild.nodeValue != None:
				ret[k] = int(n.firstChild.nodeValue)
				break		

	# range	
	for r in vnet.getElementsByTagName('RANGE'):
		scope = {}
		for rs in r.getElementsByTagName('IP_START'):
			if rs.firstChild != None and rs.firstChild.nodeValue != None:
				scope['start'] = rs.firstChild.nodeValue
				break

		for re in r.getElementsByTagName('IP_END'):
			if re.firstChild != None and re.firstChild.nodeValue != None:
				scope['end'] = re.firstChild.nodeValue
				break			

		if 'start' in scope and 'end' in scope:
			if not 'range' in ret:
				ret['range'] = scope
				break

	tplAllow = ['network-mask', 'gateway', 'dns', 'wins', 'ntp', 'domain', 'broadcast','domain-search', 'mask']
	tplPrefix = 'dhcp-'

	# template	
	for tpl in vnet.getElementsByTagName('TEMPLATE'):		
		for n in tpl.childNodes:
			if n.firstChild != None and n.firstChild.nodeValue != None:
				if not 'template' in  ret:
					ret['template'] = {}

				rtpl = ret['template']
				name = n.nodeName.lower() 
				name = name.replace('_','-')

				if not ( name in tplAllow or name.startswith(tplPrefix)):
					continue

				if name in rtpl:					
					rn = rtpl[name]

					if type(rn) is list:
						rn.append(n.firstChild.nodeValue)
					else:
						rtpl[name] = [ rn, n.firstChild.nodeValue ]

				else:
					rtpl[name] = n.firstChild.nodeValue
	
	return updateVnet(ret)


def procVnets(dom):
	ret = []
	for vnet in dom.getElementsByTagName('VNET'):
		vn = procVnet(vnet)

		if not vn is None:
			ret.append(vn)

	return ret

def prepareDnet(vnet):
	if vnet is None:
		return

	global dhcp_option_map
	cfg = vnet.copy()

	opts = cfg['template']
	del cfg['template']
	
	cfg['interface'] = cfg['bridge']
	del cfg['bridge']


	name = '%s-%s-%s' % ( cfg['name'], cfg['id'], cfg['interface'])
	name = name.lower()

	del cfg['id']
	del cfg['name']


	optsMapMulti = {'ntp': 'ntp-server', 'wins': 'netbios-ns', 'domain': 'domain-name', 'gateway': 'router', 'dns':'dns-server', 'domain-search': 'domain-search'}

	for k,v in optsMapMulti.items():
		if k in opts:
			nname = 'dhcp-' + v

			if nname in opts:
				if type(opts[nname]) is list:
					opts[nname].append(opts[k])
				else:
					opts[nname] = [ opts[nname], opts[k] ]
			else:
				opts[nname] = opts[k]

			del opts[k]

	optsfix = {}

	# removing dhcp-
	for k,v in opts.items():
		if (type(k) is str or type(k) is unicode) and k.startswith('dhcp-'):
			nk = str(k[5:])

			try:
				nk = int(nk)
			except ValueError:
				pass

			optsfix[nk]=v

	optsdel = []
	# map int -> option name
	for k in optsfix:	
		if type(k) is int and k in dhcp_option_map:									
			nk = dhcp_option_map[k]
			print nk, k

			if nk in optsfix:
				if type(optsfix[nk]) is list:
					optsfix[nk].append(optsfix[k])				
				else:
					optsfix[nk] = [ optsfix[nk], optsfix[k] ]
			else:
				optsfix[nk] = optsfix[k]

			optsdel.append(k)
		elif type(k) is str and k not in dhcp_option_map.values():
			optsdel.append(k)
			

	for d in optsdel:
		del optsfix[d]	

						
	ret = { 'name': name,  'cfg': cfg, 'opts': optsfix }	

	return ret

def prepareVnets(vnets):
	if vnets is None or type(vnets) is not list:	
		return


	ret = []

	for vnet in vnets:
		dnet = prepareDnet(vnet)

		if dnet is not None:
			ret.append(dnet)


	if len(ret) == 0:
		return
	else:
		return ret


def dnsmasqCheck():
	global dnsmasq_confd, dnsmasq_hostd, dnsmasq_optd
	toCheck = [ dnsmasq_confd, dnsmasq_hostd, dnsmasq_optd ]
	isErr = False

	for c in toCheck:
		if not os.path.isdir(c):
			print >> sys.stderr, 'Directory not found:', c
			isErr = True



	
	return not isErr

def getFiles(listDir):
	global file_prefix,file_postfix

	ret = []
	for n in os.listdir(listDir):
		if n.startswith(file_prefix) and n.endswith(file_postfix):
			ret.append(n)
	return ret


def ip2num(ip):
	return struct.unpack('!L',socket.inet_aton(ip))[0]

def num2ip(n):
	return socket.inet_ntoa(struct.pack('!L',n))

def num2hexb(n):
	bs = struct.pack('!L',n)
	ret = []
	for b in bs:
		ret.append('%02x' % (ord(b)))

	return ret


def dnsmasqGetHosts():
	global dnsmasq_hostd

	return getFiles(dnsmasq_hostd)

def dnsmasqGetConfs():
	global dnsmasq_confd

	return getFiles(dnsmasq_confd)

def dnsmasqGetOpts():
	global dnsmasq_optd

	return getFiles(dnsmasq_optd)

def dnsmasqPrepareCfg(name,cfg):
	cfg_dump = []

	cfg_dump.append('interface=%s' % (cfg['interface']))

	# generate dhcp-pange
	# dhcp-range=set:<tag>,<start>,<end>,<mode>,<netmask>,<broadcast>,<lease-time>
	dhr = 'dhcp-range=' 
	dhr_items = []

	# tag
	dhr_items.append('set:%s' % (name))

	# ranges
	dhr_items.append(cfg['range']['start'])
	dhr_items.append(cfg['range']['end'])

	# mode
	dhr_items.append('static')

	# netmask
	dhr_items.append(cfg['netmask'])

	# broadcast
	if 'broadcast' in cfg:
		dhr_items.append(cfg['broadcast'])

	# lease time
	if 'lease-time' in cfg:
		dhr_items.append(cfg['lease-time'])

	# join all together
	dhr += ','.join(dhr_items)
	cfg_dump.append(dhr)

	return cfg_dump

def dnsmasqPrepareOpts(name,opts):
	opts_dump = []

	for k,v in opts.items():
		if type(v) is list:
			v = ','.join(v)

		if type(k) is str:
			opts_dump.append('tag:%s,option:%s,%s' % (name, k, v))
		elif type(k) is int:
			opts_dump.append('tag:%s,%i,%s' % (name, k, v))

	return opts_dump

def dnsmasqPrepareHosts(name,cfg):
	global one_mac_prefix
	ret = []

	range_start = cfg['range']['start']
	range_end = cfg['range']['end']
	lease_time = None

	if 'lease-time' in cfg:
		lease_time = cfg['lease-time']

	irs = ip2num(range_start)
	ire = ip2num(range_end)

	i = irs
	while i <= ire:
		ip = num2ip(i)
		bs = num2hexb(i)

		# must be ipv4
		assert(len(bs) == 4)
		
		mac = ':'.join(bs)
		mac = ':'.join([one_mac_prefix, mac])

		# [<hwaddr>][,set:<tag>][,<ipaddr>][,<lease_time>]
		hstp = []
		
		hstp.append(mac)
		hstp.append('set:%s' % (name))
		hstp.append(ip)

		if lease_time != None:
			hstp.append(lease_time)

		hst = ','.join(hstp)
		ret.append(hst)
			
		i+=1



	return ret

def genHash(en):
	h = hashlib.md5()
	for l in en:
		l = l.strip()
		if l != '' and not l.startswith('#'):
			h.update(l)
	
	return h.hexdigest()

def genFileHash(p):
	f = open(p,'r')
	ret = genHash(f)
	f.close()
	return ret

def dnsmasqPrepare(vnet):
	global file_prefix, file_postfix
	ret = vnet.copy()
	
	name = ret['name']
	opts = ret['opts']
	cfg = ret['cfg']	

	ret['filename'] = file_prefix + name + file_postfix

	ret['cfg'] = dnsmasqPrepareCfg(name, cfg)
	ret['opts'] = dnsmasqPrepareOpts(name,opts)
	ret['hosts'] = dnsmasqPrepareHosts(name,cfg)

	hshs = {}	
	hshs['cfg'] = genHash(ret['cfg'])
	hshs['opts'] = genHash(ret['opts'])
	hshs['hosts'] = genHash(ret['hosts'])

	ret['hash'] = hshs

	return ret

def dnsmasqGetCfg(vnets):
	cfg = {}
	for vnet in vnets:
		vn = dnsmasqPrepare(vnet)
		cfg[vn['filename']] = vn

	return cfg

def dnsmasqClean(valid):
	global dnsmasq_confd, dnsmasq_hostd, dnsmasq_optd

	toCheck = {}
	toCheck[dnsmasq_confd] = dnsmasqGetConfs()
	toCheck[dnsmasq_hostd] = dnsmasqGetHosts()
	toCheck[dnsmasq_optd] = dnsmasqGetOpts()

	for k,v in toCheck.items():
		for f in v:
			if f not in valid:
				os.remove(os.path.join(k,f))
	pass

def dnsmasqUpdateFile(p,hs,ls):
	if os.path.exists(p):
		# must be a file
		assert(os.path.isfile(p))

		chs = genFileHash(p)

		if chs == hs:
			return False

	f = open(p, 'w')
	f.write('# autogenerated by opennebula-dnsmasq script' + "\n")
	f.write("\n")

	for l in ls:
		f.write(l + '\n')

	f.close()

	return True

	



def dnsmasqFill(f, cfg):
	global dnsmasq_confd, dnsmasq_hostd, dnsmasq_optd

	hup = False
	rl = False

	f_conf = os.path.join(dnsmasq_confd, f)
	f_host = os.path.join(dnsmasq_hostd, f)
	f_opt = os.path.join(dnsmasq_optd, f)

	
	# conf
	rl = dnsmasqUpdateFile(f_conf,cfg['hash']['cfg'],cfg['cfg'])

	hup = dnsmasqUpdateFile(f_host,cfg['hash']['hosts'],cfg['hosts']) or hup
	hup = dnsmasqUpdateFile(f_opt,cfg['hash']['opts'],cfg['opts']) or hup
	

	return hup,rl

def dnsmasqUpdate(cfg):
	global dsnmasq_restart, dnsmasq_reload
	dnsmasqClean(cfg.keys())

	hup = False
	rs = False

	for k,v in cfg.items():
		h,r = dnsmasqFill(k,v)
		hup = hup or h
		rs = rs or r

	if rs:
		p = subprocess.Popen([dnsmasq_restart], shell=True, stdout=subprocess.PIPE)
		assert(p.wait() == 0)

	elif hup:		
		p = subprocess.Popen([dnsmasq_reload], shell=True, stdout=subprocess.PIPE)
		assert(p.wait() == 0)

	pass

def main():
	global dhcp_option_map
	if not dnsmasqCheck():
		return -1

	dhcp_option_map = getOptionMap()
	dom = getXml()

	if dom is None:
		return

	vnets = procVnets(dom)
	vnets = prepareVnets(vnets)

	#print jsonDump(vnets)

	if vnets is None:
		print 'VNets not found'
		return

	dnCfg = dnsmasqGetCfg(vnets)
	dnsmasqUpdate(dnCfg)	

	pass


if __name__ == '__main__':
	try:
		ret = main()
		sys.exit(ret)
	except:
		raise

