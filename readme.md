# Scripts

* __one-dnsmasq.py__ - dsnmasq auto configuration
* __hook_poweroff.rb__ - automaticaly recover VMS in _POWEROFF_ state 
which is not initiated by OpenNebula (for example on host reboot or shutdown in VM)

# Cron.d
cron example configs for scripts

# hook_poweroff.rb
Please configure following __VM_HOOK__ in _oned.conf_:
```
VM_HOOK = [
    name      = "handle_power_off",
    on        = "CUSTOM",
    state     = "POWEROFF",
    lcm_state = "LCM_INIT",
    command   = "<CHEKOUT_DIRECTORY>/scripts/hook_poweroff.rb",
    arguments = "$ID $TEMPLATE"
]
```