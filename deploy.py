#!/usr/bin/env python

import argparse
import logging
import os
import threading
import subprocess

command_list = ('list', 'delete', 'push', 'add')

BASE_DIR = './.deploy'
TARGET_CONF = os.path.join(BASE_DIR, 'deploy_targets.conf')


def parse_file(target_file_path):
    """
    parse conf file and return a dictionary of targets where the keys are
    the local branch name and the values are a list of
    <remote>:<remote_branch> strings
    """
    with open(target_file_path, 'r') as target_file:
        targets = {}
        for line in target_file:
            entries = [x.strip() for x in line.split(' ') if x.strip() != '']
            if len(entries) < 2:
                logging.debug('skipping line in target conf file. Not enough values to unpack: {0}'.format(entries))
                continue
            branch = entries[0]
            remotes = entries[1:]
            targets[branch] = remotes
        return targets


def write_file(target_file_path, targets):
    """
    write dictionary of targets to conf file
    """
    with open(target_file_path, 'w') as target_file:
        for branch, remotes in targets.iteritems():
            target_file.write(branch)
            for remote in remotes:
                target_file.write(" ")
                target_file.write(remote)
            target_file.write("\n")


def call(cmd, output=False, *args, **kwargs):
    """
    call system command, optionally returning output
    """
    logging.debug('calling command: {0}'.format(cmd))
    if output:
        return subprocess.check_output(cmd, shell=True, *args, **kwargs)
    else:
        return subprocess.call(cmd, shell=True, *args, **kwargs)


def print_target(branch, remotes):
    """
    pretty print a target
    """
    print "{0}{1}".format(branch.ljust(26, ' '), [r.strip() for r in remotes])


def find_missing_git_remotes(remotes_to_check):
    """
    check that each value in a list of strings is an existing git remote
    returns the name of the first missing remote (if any), or None if all
    remotes exist
    """
    git_remotes = call('git remote', output=True).split('\n')
    for remote in remotes_to_check:
        if ':' in remote:
            remote_name, remote_branch = remote.split(':')
        else:
            remote_name = remote
        if remote_name not in git_remotes:
            return remote
    return None


def list_cmd(targets):
    """
    list command: list all targets
    Returns True if successful, otherwise False
    """
    if len(targets) < 1:
        logging.error('No targets exist')
        return False
    print 'BRANCH (local_branch)'.ljust(25, ' '), 'REMOTES [<remote>:<remote_branch>]'
    for branch, remotes in targets.iteritems():
        print_target(branch, remotes)
    return True


def delete(targets, branch_name):
    """
    delete command: delete target associated with <branch_name> local branch
    Returns the updated targets dict
    """
    if branch_name not in targets:
        logging.error('No such deploy target: {0}'.format(branch_name))
        return targets
    print 'You are about to delete the following deploy target:'
    print_target(branch_name, targets[branch_name])
    x = raw_input('Continue? (y/N): ')
    if 'y' not in x.lower():
        print 'Cancelling...'
        return targets
    del targets[branch_name]
    logging.debug('{0} target deleted'.format(branch_name))
    return targets


def push(targets, branch_name, multithread=False, force=False):
    """
    push command: push local branch <branch_name> to all associated remotes
    Returns True if successful, otherwise False
    """
    # Check that branch_name target exists in target file
    if branch_name not in targets:
        logging.error('No such deploy target: {0}'.format(branch_name))
        return False

    # Check that working tree has no modifications
    if call('git diff --quiet && git diff --cached --quiet'):
        logging.error('working tree has modifications')
        return False

    # Check that branch_name git branch exists
    branches = call('git branch --list', output=True).split("\n")
    branches = [x.strip('* ') for x in branches if x != '']
    if branch_name not in branches:
        logging.error('no such local branch')
        return False

    # Checkout branch
    logging.info('checking out {0} branch'.format(branch_name))
    if call('git checkout {0} --quiet'.format(branch_name)):
        logging.error('failed to checkout branch')
        return False

    # TODO: should we fetch/pull here?

    # push to each remote...
    remote_log_dir = os.path.join(BASE_DIR, branch_name.replace('/', '-'))
    if not os.path.exists(remote_log_dir):
        os.mkdir(remote_log_dir)

    open_threads = []
    results = []
    for remote in targets[branch_name]:
        pid = targets[branch_name].index(remote)
        if ":" in remote:
            remote_name, remote_branch = remote.split(':')
        else:
            remote_name = remote
            remote_branch = branch_name
        branch_log = os.path.join(remote_log_dir, remote_name) + '.out'

        def push_remote(_pid, _remote_name, _branch_name, _remote_branch, _force, _branch_log):
            with open(_branch_log, 'w+') as target_log:
                cmd = 'git push {0} {1}:{2} {3}'.format(
                    _remote_name, _branch_name, _remote_branch, '--force' if _force else ''
                )
                res = call(cmd, output=False, stdout=target_log, stderr=target_log)
                logging.info('process {0} finished with exit code {1}'.format(_pid, res))
                results.append(res)
        t = threading.Thread(
            target=push_remote,
            args=(pid, remote_name, branch_name, remote_branch, force, branch_log)
        )
        t.start()
        logging.info('process {4}: Pushing {0} local branch to {1}:{2}. Logging output to {3}'.format(branch_name, remote_name, remote_branch, branch_log, pid))
        if not multithread:
            t.join()
        else:
            open_threads.append(t)

    if multithread:
        for t in open_threads:
            t.join()
    for result in results:
        if results:
            return False
    return True


def add(targets, branch_name, remotes):
    """
    add command: add a target associating local branch 'branch_name' to a list of 'remotes'
    'remotes' is a list of <remote>:<remote_branch> strings
    if the :<remote_branch> is omitted, 'branch_name' will be used for both
    the local and remote branch
    Returns the updated targets dict
    """
    if branch_name in targets:
        print 'target branch already exists. Continuing will overwrite existing target'
        x = raw_input('Continue? (y/N)')
        if 'y' not in x.lower():
            print 'Cancelling...'
            return targets
    missing_remote = find_missing_git_remotes(remotes)
    if missing_remote:
        logging.error('git remote does not exist: {0}'.format(missing_remote))
        return targets
    targets[branch_name] = remotes
    return targets


def main(args, loglevel):
    logging.basicConfig(format="%(levelname)s: %(message)s", level=loglevel)
    if not os.path.exists(BASE_DIR):
        os.mkdir(BASE_DIR)
    if not os.path.exists(TARGET_CONF):
        open(TARGET_CONF, 'w+').close()

    command = args.command.lower()
    if command not in command_list:
        logging.error('invalid command. choices are {0}'.format(command_list))
        exit(1)

    targets = parse_file(TARGET_CONF)

    if command == 'list':
        if list_cmd(targets):
            exit(0)
        exit(1)

    if not args.branch:
        logging.error('This command requires a target branch')
        exit(1)
    branch_name = args.branch.lower()
    if command == 'delete':
        targets = delete(targets, branch_name)
        write_file(TARGET_CONF, targets)
        exit(0)
    elif command == 'push':
        if push(targets, branch_name, multithread=args.multithread, force=args.force):
            exit(0)
        exit(1) 
    remotes = args.remotes
    if not remotes:
        logging.error('This command requires at least one remote')
        exit(1)
    if command == 'add':
        targets = add(targets, branch_name, remotes)
        write_file(TARGET_CONF, targets)
        exit(0)
    logging.error('unknown error')
    exit(1)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description="Tool for managing and pushing local git branches to various git remotes and branches on those remotes",
        epilog="""
This tool allows users to associate a local branch with a list of git remotes (and branches on those remotes) \
and quickly push the local branch to all associated remotes.

A target includes a single local branch plus one or more remote:remote_branch values. If the :remote_branch portion is omitted,\
 the name of the local branch will be used. Targets are identified by the name of the local branch.

The list, add, and delete commands allow users to manage their list of targets

The push command pushes the target's local branch to each of the associated remote:remote_branch values.

The list of targets is stored in a configuration file located at {target_conf}

During a push command, output from the git push call is directed to a file located at {base_dir}/<target>/<remote>.out

If a target includes multiple remotes, the push calls are run simultaneously in separate processes
                """.format(target_conf=TARGET_CONF, base_dir=BASE_DIR),
        fromfile_prefix_chars='@',
        formatter_class=argparse.RawTextHelpFormatter
    )

    parser.add_argument(
        "command",
        help="""options:\ncommand    required args:\n   list   \n   delete  <branch>\n   push    <branch>\n   add     <branch> <remote> [<remote>...]""",
        metavar="command"
    )

    parser.add_argument(
        "branch",
        help="target (local) branch",
        metavar="branch",
        nargs="?"
    )

    parser.add_argument(
        "remotes",
        metavar='remotes',
        type=str,
        nargs='*',
        help='list of git remotes in the format <remote_name>:<remote_branch_name>.\
        If the :<remote_branch_name> is omitted, the associated local branch will be used',
    )

    parser.add_argument(
        "-v",
        "--verbose",
        help="increase output verbosity",
        action="store_true"
    )

    parser.add_argument(
        "--force",
        help="force push to remotes",
        action='store_true'
    )

    parser.add_argument(
        "-m",
        "--multithread",
        help="push to all target remotes in concurrent threads",
        action='store_true',
    )

    args = parser.parse_args()

    # Setup logging
    if args.verbose:
        loglevel = logging.DEBUG
    else:
        loglevel = logging.INFO

    main(args, loglevel)
