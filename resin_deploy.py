#!/usr/bin/env python
#

# import modules used here -- sys is a very standard one
import sys, argparse, logging, os, threading

from subprocess import call, check_output, Popen, STDOUT, PIPE

command_list = ('list', 'delete', 'push', 'add')

BASE_DIR = './.resin_deploy'

def parse_file(target_file_path):
  with open(target_file_path, 'r') as target_file:
    targets = {}
    for line in target_file:
      entries = [x.strip() for x in line.split(' ') if x.strip() != '']
      if len(entries) < 2:
        continue
      branch = entries[0]
      remotes = entries[1:]
      targets[branch] = remotes
    return targets

def write_file(target_file_path, targets):
  with open(target_file_path, 'w') as target_file:
    for branch, remotes in targets.iteritems():
      target_file.write(branch)
      for remote in remotes:
        target_file.write(" ")
        target_file.write(remote)
      target_file.write("\n")

def print_target(branch, remotes):
  print "{0}{1}".format(branch.ljust(26, ' '), [r.strip() for r in remotes])

def find_missing_git_remotes(remotes_to_check):
  git_remotes = check_output('git remote', shell=True).split('\n')
  for remote in remotes_to_check:
    if ':' in remote:
      remote_name, remote_branch = remote.split(':')
    else:
      remote_name = remote
    if remote_name not in git_remotes:
      return remote
  return None


def list(targets):
  if len(targets) < 1:
    print 'No targets exist'
    return
  print 'BRANCH (local_branch)'.ljust(25, ' '), 'REMOTES [<remote>:<remote_branch>]'
  for branch, remotes in targets.iteritems():
      print_target(branch, remotes)

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
  return targets

def push(targets, branch_name, force=False):
  # Check that branch_name target exists in target file
  if branch_name not in targets:
    print 'target does not exist: ', branch_name
    return False
  # Check that working tree has not modifications
  if call('git diff --quiet && git diff --cached --quiet', shell=True):
    print 'working tree has modifications'
    return False
  # Check that branch_name git branch exists
  branches = check_output('git branch --list', shell=True).split("\n")
  branches = [x.strip('* ') for x in branches if x != '']
  if branch_name not in branches:
    print 'no such local branch'
    return False

  # Checkout branch
  if call('git checkout {0}'.format(branch_name), shell=True):
    print 'failed to checkout branch'
    return False

   # TODO: should we fetch/pull here?

   # push to each remote...
  remote_log_dir = os.path.join(BASE_DIR, branch_name)
  if not os.path.exists(remote_log_dir):
    os.mkdir(remote_log_dir)

  open_threads = []
  for remote in targets[branch_name]:
    if ":" in remote:
      remote_name, remote_branch = remote.split(':')
    else:
      remote_name = remote
      remote_branch = branch_name
    branch_log = os.path.join(remote_log_dir, remote_name) + '.out'
    def push_remote():
      with open(branch_log, 'w+') as target_log:
        cmd = 'git push {0} {1}:{2} {3}'.format(remote_name, branch_name, remote_branch, '--force' if force else '')
        p = Popen(cmd, shell=True, stdout=target_log, stderr=target_log)
        res = p.wait()
        print 'process {0} finished with exit code {1}'.format(targets.index(remote), res)
    t = threading.Thread(target=push_remote)
    t.start()
    print 'process {4}: Pushing {0} local branch to {1}:{2}. Logging output to {3}'.format(branch_name, remote_name, remote_branch, branch_log, targets.index(remote))
    open_threads.append(t)

  for t in open_threads:
    t.join()
  print 'push successful!'
  return True

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
  if not os.path.exists(args.file):
    open(args.file, 'w+').close()
  command = args.command.lower()
  if command not in command_list:
    print 'invalid command. choices are', command_list
    return False

  targets = parse_file(args.file)
  
  if command == 'list':
    list(targets)
    return True
  
  if not args.branch:
    print 'This command requires a target branch'
    return False
  branch_name = args.branch.lower()
  if command == 'delete':
    targets = delete(targets, branch_name)
    write_file(args.file, targets)
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
    write_file(args.file, targets)
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
                                    description = "Does a thing to some stuff.",
                                    epilog = "As an alternative to the commandline, params can be placed in a file, one per line, and specified on the commandline like '%(prog)s @params.conf'.",
                                    fromfile_prefix_chars = '@' )

  parser.add_argument(
                      "command",
                      help = "options: add, list, delete, push",
                      metavar = "command")  
  parser.add_argument(
                      "branch",
                      help = "target branch",
                      metavar = "branch",
                      nargs="?")

  parser.add_argument("remotes",
                      metavar='remotes',
                      type=str,
                      nargs='*',
                      help='list of git remotes',
                      )

  parser.add_argument(
                      "-v",
                      "--verbose",
                      help="increase output verbosity",
                      action="store_true")

  parser.add_argument(
                      "-f",
                      "--file",
                      help="file to load/store target branch list. defaults to .resin_targets",
                      default='./.resin_deploy/resin_targets.conf')

  parser.add_argument(
                      "--force",
                      help="force push to remotes",
                      action='store_true',)

  # subparsers = parser.add_subparsers(dest="subparser_add")

  # add_parser = subparsers.add_parser('add')



  args = parser.parse_args()
  
  # Setup logging
  if args.verbose:
    loglevel = logging.DEBUG
  else:
    loglevel = logging.INFO
  
  main(args, loglevel)