#!/usr/bin/env python
#

# import modules used here -- sys is a very standard one
import sys, argparse, logging, os, threading

# from subprocess import call, check_output, Popen, STDOUT, PIPE
import subprocess 

command_list = ('list', 'delete', 'push', 'add')

BASE_DIR = './.deploy'
TARGET_CONF = os.path.join(BASE_DIR, 'deploy_targets.conf')

global verbose

# parse conf file and return a dictionary of targets where the keys are 
# the local branch name and the values are a list of <remote>:<remote_branch> strings
def parse_file(target_file_path):
  with open(target_file_path, 'r') as target_file:
    targets = {}
    for line in target_file:
      entries = [x.strip() for x in line.split(' ') if x.strip() != '']
      if len(entries) < 2:
        if verbose:
          print 'skipping line in target conf file. Not enough values to unpack: ', entries
        continue
      branch = entries[0]
      remotes = entries[1:]
      targets[branch] = remotes
    return targets

# write dictionary of targets to conf file
def write_file(target_file_path, targets):
  with open(target_file_path, 'w') as target_file:
    for branch, remotes in targets.iteritems():
      target_file.write(branch)
      for remote in remotes:
        target_file.write(" ")
        target_file.write(remote)
      target_file.write("\n")

def call(cmd, output=False, *args, **kwargs):
  if verbose:
    print 'calling command: ', cmd
  if output:
    return subprocess.check_output(cmd, shell=True, *args, **kwargs)
  else:
    return subprocess.call(cmd, shell=True, *args, **kwargs)

def print_target(branch, remotes):
  print "{0}{1}".format(branch.ljust(26, ' '), [r.strip() for r in remotes])

# check that each value in a list of strings is an existing git remote
# returns the name of the first missing remote (if any), or None if all remotes exist
def find_missing_git_remotes(remotes_to_check):
  git_remotes =call('git remote', output=True).split('\n')
  for remote in remotes_to_check:
    if ':' in remote:
      remote_name, remote_branch = remote.split(':')
    else:
      remote_name = remote
    if remote_name not in git_remotes:
      return remote
  return None

# list command: list all targets
def list(targets):
  if len(targets) < 1:
    print 'No targets exist'
    return
  print 'BRANCH (local_branch)'.ljust(25, ' '), 'REMOTES [<remote>:<remote_branch>]'
  for branch, remotes in targets.iteritems():
      print_target(branch, remotes)

# delete command: delete target associated with <branch_name> local branch
def delete(targets, branch_name):
  if branch_name not in targets:
    print 'No such deploy target'
    return targets
  print 'Warning. You are about to delete the following deploy target:'
  print_target(branch_name, targets[branch_name])
  x = raw_input('Continue? (y/N): ')
  if 'y' not in x.lower():
    print 'Cancelling...'
    return targets
  del targets[branch_name]
  if verbose:
    print branch_name, ' target deleted'
  return targets

# push command: push local branch <branch_name> to all associated remotes
def push(targets, branch_name, force=False):
  # Check that branch_name target exists in target file
  if branch_name not in targets:
    print 'target does not exist: ', branch_name
    return False

  # Check that working tree has not modifications
  if call('git diff --quiet && git diff --cached --quiet'):
    print 'working tree has modifications'
    return False

  # Check that branch_name git branch exists
  branches = call('git branch --list', output=True).split("\n")
  branches = [x.strip('* ') for x in branches if x != '']
  if branch_name not in branches:
    print 'no such local branch'
    return False

  # Checkout branch
  print 'checking out {0} branch'.format(branch_name)
  if call('git checkout {0} --quiet'.format(branch_name)):
    print 'failed to checkout branch'
    return False

   # TODO: should we fetch/pull here?

   # push to each remote...
  remote_log_dir = os.path.join(BASE_DIR, branch_name)
  if not os.path.exists(remote_log_dir):
    os.mkdir(remote_log_dir)

  open_threads = []
  for remote in targets[branch_name]:
    pid = targets[branch_name].index(remote)
    if ":" in remote:
      remote_name, remote_branch = remote.split(':')
    else:
      remote_name = remote
      remote_branch = branch_name
    branch_log = os.path.join(remote_log_dir, remote_name) + '.out'
    def push_remote():
      my_pid = pid
      with open(branch_log, 'w+') as target_log:
        cmd = 'git push {0} {1}:{2} {3}'.format(remote_name, branch_name, remote_branch, '--force' if force else '')
        res = call(cmd, output=False, stdout=target_log, stderr=target_log)
        print 'process {0} finished with exit code {1}'.format(my_pid, res)
    t = threading.Thread(target=push_remote)
    t.start()
    print 'process {4}: Pushing {0} local branch to {1}:{2}. Logging output to {3}'.format(branch_name, remote_name, remote_branch, branch_log, pid)
    open_threads.append(t)

  for t in open_threads:
    t.join()
  return True

# add command: add a target associating local branch 'branch_name' to a list of 'remotes'
# 'remotes' is a list of <remote>:<remote_branch> strings
# if the :<remote_branch> is omitted, 'branch_name' will be used for both the local and remote branch
def add(targets, branch_name, remotes):
  if branch_name in targets:
    print 'target branch already exists. Continuing will overwrite existing target'
    x = raw_input('Continue? (y/N)')
    if 'y' not in x.lower():
      print 'Cancelling...'
      return targets
  missing_remote = find_missing_git_remotes(remotes)
  if missing_remote:
    print 'git remote does not exist: ', missing_remote
    return targets
  targets[branch_name] = remotes
  return targets

def process_commands(args):
  if not os.path.exists(BASE_DIR):
    os.mkdir(BASE_DIR)
  if not os.path.exists(TARGET_CONF):
    open(TARGET_CONF, 'w+').close()
  command = args.command.lower()
  if command not in command_list:
    print 'invalid command. choices are', command_list
    return False

  targets = parse_file(TARGET_CONF)
  
  if command == 'list':
    list(targets)
    return True
  
  if not args.branch:
    print 'This command requires a target branch'
    return False
  branch_name = args.branch.lower()
  if command == 'delete':
    targets = delete(targets, branch_name)
    write_file(TARGET_CONF, targets)
    return True
  elif command == 'push':
    push(targets, branch_name, force=args.force)
    return True
  remotes = args.remotes
  if not remotes:
    print 'This command requires at least one remote'
    return False
  if command == 'add':
    targets = add(targets, branch_name, remotes)
    write_file(TARGET_CONF, targets)
    return True
  return False


# Gather our code in a main() function
def main(args, loglevel):
  logging.basicConfig(format="%(levelname)s: %(message)s", level=loglevel)
  
  process_commands(args)
 
# Standard boilerplate to call the main() function to begin
# the program.
if __name__ == '__main__':
  parser = argparse.ArgumentParser( 
                                    description = "Tool for managing and pushing local git branches to various git remotes and branches on those remotes",
                                    epilog = """
This tool allows users to associate a local branch with a list of git remotes (and branches on those remotes) \
and quickly push the local branch to all associated remotes.

A target includes a single local branch plus one or more remote:remote_branch values. If the :remote_branch portion is omitted,\
 the name of the local branch will be used. Targets are identified by the name of the local branch.

The list, add, and delete commands allow users to manage their list of targets

The push command pushes the target's local branch to each of the associated remote:remote_branch values.

The list of targets is stored in a configuration file located at {target_conf}

During a push command, output from the git push call is directed to a file located at {base_dir}/<target>/<remote>.out

If a target includes multiple remotes, the push calls are run simultaneously in separate processes
                                    """.format( target_conf=TARGET_CONF,
                                                base_dir=BASE_DIR,
                                              ),
                                    fromfile_prefix_chars = '@',
                                    formatter_class=argparse.RawTextHelpFormatter)

  parser.add_argument(
                      "command",
                      help = """options:\ncommand    required args:\n   list   \n   delete  <branch>\n   push    <branch>\n   add     <branch> <remote> [<remote>...]""",
                      metavar = "command")  
  parser.add_argument(
                      "branch",
                      help = "target (local) branch",
                      metavar = "branch",
                      nargs="?")

  parser.add_argument("remotes",
                      metavar='remotes',
                      type=str,
                      nargs='*',
                      help='list of git remotes in the format <remote_name>:<remote_branch_name>. If the :<remote_branch_name> is omitted, the associated local branch will be used',
                      )

  parser.add_argument(
                      "-v",
                      "--verbose",
                      help="increase output verbosity",
                      action="store_true")

  parser.add_argument(
                      "--force",
                      help="force push to remotes",
                      action='store_true',)


  args = parser.parse_args()
  global verbose
  verbose = args.verbose
  
  # Setup logging
  if args.verbose:
    loglevel = logging.DEBUG
  else:
    loglevel = logging.INFO
  
  main(args, loglevel)