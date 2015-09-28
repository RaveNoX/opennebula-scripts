#!/usr/bin/env ruby

require 'pp'
require 'base64'
require 'nokogiri'

## 
# Opennebula
##
ONE_LOCATION=ENV["ONE_LOCATION"]

if !ONE_LOCATION
      RUBY_LIB_LOCATION="/usr/lib/one/ruby"
else
      RUBY_LIB_LOCATION=ONE_LOCATION+"/lib/ruby"
end

$: << RUBY_LIB_LOCATION

require 'opennebula'
##
# Opennebula end
##

def select_cmd(id, lastAction)
  unless %w{poweroff poweroff-hard}.include? lastAction
    return "onevm resume #{id}"
  end  
end

def main(args)
  if args.length < 2
    STDERR.puts "Usage: $0 ID TEMPLATE"
    return 1
  end

  begin
    id = Integer(args[0])
  rescue ArgumentError
    STDERR.puts "Invalid ID: #{args[0]}"
    return 2
  end

  tpl = args[1].strip

  if tpl.empty? 
    STDERR.puts "Empty TEMPLATE: #{args[1]}"
    return 2
  end

  begin 
    tpl = Base64.decode64(tpl)
    tpl = Nokogiri::XML(tpl)
  rescue => err
    STDERR.puts "Cannot parse TEMPLATE: #{err}"
    return 3
  end

  begin

  hist = tpl.xpath('/VM/HISTORY_RECORDS/HISTORY[last()]/ACTION').first

    if hist == nil
      STDERR.puts "Cannot find last HISTORY item"
      return 4
    end
  
    lastAction = Integer(hist.content)
  rescue
    STDERR.puts "Cannot parse HISTORY ACTION: #{host.content}"
    return 5
  end
 
  lastAction = OpenNebula::VirtualMachine::HISTORY_ACTION[lastAction]

  cmd = select_cmd(id, lastAction)

  if cmd != nil
    puts "Executing command: #{cmd}"
    system(cmd)
    puts "Exit code: #{$?.exitstatus}"

    unless $?.success?
      return 10
    end    
  else
    puts "No action required"
  end
end

# Entry point
if $0 == __FILE__
  begin
    ret = main(ARGV)

    if ret == nil || !ret.is_a?(Integer)
      exit 0
    end

    exit ret
  rescue Interrupt
    puts 'Exit by CTRL+C'
    exit -1
  end
end

# vim: ai ts=2 sts=2 et sw=2 ft=ruby
# vim: autoindent tabstop=2 shiftwidth=2 expandtab softtabstop=2 filetype=ruby
