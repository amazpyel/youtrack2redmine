import base64
import os
import shutil
import time
import sys
import xml.etree.ElementTree as ET
from xml.dom import minidom
from youtrack.connection import Connection
from redmine import Redmine
from redmine.exceptions import ServerError

import youtrack2redmineMap


def download_attachments(folder_name):
    create_folder(folder_name)
    filenames = []
    i = 0
    for attachment in youtrack.getAttachments(folder_name):
        i += 1
        attachment_filename = attachment.name.replace(' ', '_').replace(':', '_')
        if attachment_filename in filenames:
            attachment_filename = attachment.name.replace(' ', '_').replace(':', '_') + "_" + str(i)
        else:
            attachment_filename = attachment.name.replace(' ', '_').replace(':', '_')
        filenames.append(attachment_filename)
        attachment_file = youtrack.getAttachmentContent(attachment.url)
        CHUNK = 16 * 1024
        fp = open(folder_name + "\\" + attachment_filename, 'wb')
        while True:
            chunk = attachment_file.read(CHUNK)
            if not chunk:
                break
            fp.write(chunk)
        fp.close()
        attachment_file.close()


def redmine_get_project_id(project_name):
    return redmine.project.get(project_name).id


def create_folder(path_to_folder):
    if not os.path.exists(path_to_folder):
        try:
            os.makedirs(path_to_folder)
        except WindowsError as win_exc:
            print win_exc
            exit()


def get_redmine_users():
    users = redmine.user.all()
    rdmn_users = {}
    for user in users:
        rdmn_users[user.login.lower()] = user.id
    return rdmn_users


def get_redmine_trackers():
    trackers = redmine.tracker.all()
    rdmn_trackers = {}
    for tracker in trackers:
        rdmn_trackers[tracker.name] = tracker.id
    return rdmn_trackers


def get_redmine_priorities():
    priorities = redmine.enumeration.filter(resource='issue_priorities')
    rdmn_priorities = {}
    for priority in priorities:
        rdmn_priorities[priority.name] = priority.id
    return rdmn_priorities


def get_redmine_statuses():
    statuses = redmine.issue_status.all()
    rdmn_statuses = {}
    for status in statuses:
        rdmn_statuses[status.name] = status.id
    return rdmn_statuses


def get_redmine_project_versions():
    rdmn_versions = redmine.project.get(REDMINE_PROJECT).versions
    redmine_project_versions = {}
    for version in rdmn_versions:
        redmine_project_versions[version.name] = version.id
    return redmine_project_versions


def get_redmine_custom_fields():
    fields = redmine.custom_field.all()
    rdmn_custom_fields = {}
    for field in fields:
        rdmn_custom_fields[field.name] = field.id
    return rdmn_custom_fields


def clear_folder(folder):
    shutil.rmtree(folder, ignore_errors=True)


def set_planfixdate():
    if hasattr(youtrack_issue, 'PlanFix date'):
        year = time.strftime('%Y', time.gmtime(int(youtrack_issue['PlanFix date']) / 1000.))
        month = time.strftime('%m', time.gmtime(int(youtrack_issue['PlanFix date']) / 1000.))
        if len(month) == 1:
            month = '0' + month
        day = int(time.strftime('%d', time.gmtime(int(youtrack_issue['PlanFix date']) / 1000.)))
        date_issue = str(year) + '-' + str(month) + '-' + str(day)
        redmine_issue.custom_fields = [
            {
                'id': redmine_custom_fields[youtrack2redmineMap.other_fields['PlanFix date']],
                'value': str(date_issue)
            }
        ]


def set_storypoints():
    if hasattr(youtrack_issue, 'Estimation'):
        redmine_issue.custom_fields = [
            {
                'id': redmine_custom_fields[youtrack2redmineMap.other_fields['Estimation']],
                'value': int(youtrack_issue['Estimation'])
            }
        ]


def set_estimation():
    if hasattr(youtrack_issue, 'Estimation (EHR)'):
        redmine_issue.estimated_hours = int(youtrack_issue['Estimation (EHR)']) / 60
    redmine_issue.priority_id = redmine_priorities[youtrack2redmineMap.priority[youtrack_issue.Priority]]


def set_status():
    if hasattr(youtrack_issue, 'State'):
        try:
            redmine_issue.status_id = redmine_statuses[youtrack2redmineMap.state2status[youtrack_issue.State]]
        except KeyError:
            pass


def set_type():
    redmine_issue.tracker_id = redmine_trackers[youtrack2redmineMap.type2tracker[youtrack_issue['Type']]]


def set_affected_versions():
    if hasattr(youtrack_issue, 'Affected version'):
        if type(youtrack_issue['Affected version']) == list:
            affected_versions = []
            for version in youtrack_issue['Affected version']:
                try:
                    affected_versions.append(redmine_versions[youtrack2redmineMap.affected_version[version]])
                except KeyError:
                    pass
            redmine_issue.custom_fields = [
                {
                    'id': redmine_custom_fields[youtrack2redmineMap.other_fields['Affected version']],
                    'value': tuple(affected_versions)
                }
            ]
        else:
            redmine_issue.custom_fields = [
                {
                    'id': redmine_custom_fields[youtrack2redmineMap.other_fields['Affected version']],
                    'value': redmine_versions[
                        youtrack2redmineMap.affected_version[youtrack_issue['Affected version']]]
                }
            ]


def set_assignee():
    if hasattr(youtrack_issue, 'Assignee'):
        redmine_issue.assigned_to_id = redmine_users[youtrack_issue['Assignee']]


def add_attachments():
    download_attachments(issue_id)
    attachments = [parentdir + "\\" + issue_id + "\\" + x for x in os.listdir(parentdir + "\\" + issue_id)]
    uploads_paths = []
    for attachment in attachments:
        uploads_paths.append({'path': attachment, 'filename': attachment.split('\\')[-1]})
    redmine_issue.uploads = uploads_paths


def sey_subject():
    redmine_issue.subject = youtrack_issue.summary


def set_description():
    if hasattr(youtrack_issue, 'description'):
        redmine_issue.description = '*Originally reported by*: ' + youtrack_issue['reporterFullName'] + '\n\n' + \
                                    youtrack_issue['description']
    else:
        redmine_issue.description = '*Originally reported by*: ' + youtrack_issue['reporterFullName']


def add_comments():
    saved_issue = redmine.issue.get(redmine_issue.id)
    for comment in youtrack.getComments(issue_id):
        saved_issue.notes = '*' + str(comment.author) + '*' + ':\n' + comment.text
        saved_issue.save()


def delete_folder():
    shutil.rmtree(issue_id, ignore_errors=True)


def set_parents():
    parents_list = youtrack.getIssues('Parent for: ' + str(yt_issue), 0, 3000)
    if len(parents_list) != 0:
        try:
            child_issue = redmine.issue.get(rdmn_issue)
            child_issue.parent_issue_id = issues_dict[parents_list[0].id]
            child_issue.save()
        except KeyError:
            pass


def set_relates():
    relates_list = youtrack.getIssues('Relates to: ' + str(yt_issue), 0, 3000)
    if len(relates_list) != 0:
        for relate_issue in relates_list:
            relation = redmine.issue_relation.new()
            relation.issue_id = rdmn_issue
            try:
                relation.issue_to_id = issues_dict[relate_issue.id]
                relation.relation_type = 'relates'
                relation.save()
            except KeyError:
                pass


def set_depends():
    depends_list = youtrack.getIssues('Depends on: ' + str(yt_issue), 0, 3000)
    if len(depends_list) != 0:
        for depend_issue in depends_list:
            depend_relation = redmine.issue_relation.new()
            depend_relation.issue_id = issues_dict[depend_issue.id]
            depend_relation.issue_to_id = rdmn_issue
            depend_relation.relation_type = 'blocks'
            depend_relation.save()


def set_duplicates():
    duplicates_list = youtrack.getIssues('Duplicates: ' + str(yt_issue), 0, 3000)
    if len(duplicates_list) != 0:
        for duplicate_issue in duplicates_list:
            duplicate_relation = redmine.issue_relation.new()
            duplicate_relation.issue_id = issues_dict[duplicate_issue.id]
            duplicate_relation.issue_to_id = rdmn_issue
            duplicate_relation.relation_type = 'duplicates'
            duplicate_relation.save()


def get_tracking(id):
    response, content = youtrack._req('GET', '/issue/' + id + '/timetracking/workitem/')
    xml = minidom.parseString(content)
    return xml.toxml().encode('utf-8')


def add_tracking():
    tracking_info = youtrack.get_tracking(yt_issue)
    root = ET.fromstring(tracking_info)
    if len(root.findall('workItem')) != 0:
        for workItem in root.findall('workItem'):
            date_issue = workItem.find('date').text
            duration = str(int(round(float(workItem.find('duration').text) / 60)))
            try:
                description = workItem.find('description').text
            except AttributeError:
                pass
            year = time.strftime('%Y', time.gmtime(int(date_issue) / 1000.))
            month = time.strftime('%m', time.gmtime(int(date_issue) / 1000.))
            if len(month) == 1:
                month = '0' + month
            day = time.strftime('%d', time.gmtime(int(date_issue) / 1000.))
            date_issue = str(year) + '-' + str(month) + '-' + str(day)
            attempts = 0
            while attempts < 3:
                try:
                    time_entry = redmine.time_entry.new()
                    time_entry.issue_id = rdmn_issue
                    time_entry.spent_on = date_issue
                    time_entry.hours = duration
                    time_entry.activity_id = 2
                    try:
                        time_entry.comments = description[0:255]
                    except:
                        pass
                    time_entry.save()
                    break
                except ServerError as e:
                    time.sleep(1)
                    attempts += 1
                    print e


if __name__ == '__main__':
    start_time = time.time()
    parentdir = os.path.dirname(os.path.realpath(__file__))
    sys.path.append(parentdir)

    LOGIN = ''
    PASSWRD = base64.b64decode('encrypted password')
    YOUTRACK_URL = 'youtrack url'
    REDMINE_URL = 'redmine url'
    REDMINE_API_KEY = 'api key'
    REDMINE_PROJECT = 'redmine project name'
    YOUTRACK_PROJECT = 'youtrack project id'
    SEARCH_QUERY = 'youtrack search query'

    youtrack = Connection(YOUTRACK_URL, LOGIN, PASSWRD)
    redmine = Redmine(REDMINE_URL, key=REDMINE_API_KEY, requests={'verify': False})

    issues_list = youtrack.getIssues('project: ' + YOUTRACK_PROJECT + SEARCH_QUERY, 0, 1000)

    redmine_users = get_redmine_users()
    redmine_trackers = get_redmine_trackers()
    redmine_statuses = get_redmine_statuses()
    redmine_priorities = get_redmine_priorities()
    redmine_versions = get_redmine_project_versions()
    redmine_custom_fields = get_redmine_custom_fields()

    issues_dict = {}
    print "This script makes a copy of issues from YouTrack to Redmine"
    print "==========Copying from YouTrack to Redmine=========="
    for issue in issues_list:
        issue_id = issue.id
        youtrack_issue = youtrack.getIssue(id=issue_id)
        print "Processing " + youtrack_issue.id + " " + youtrack_issue.summary
        redmine_issue = redmine.issue.new()
        redmine_issue.project_id = redmine.project.get(REDMINE_PROJECT).id
        set_assignee()
        sey_subject()
        set_type()
        set_status()
        set_estimation()
        set_storypoints()
        set_planfixdate()
        set_affected_versions()
        set_description()
        add_attachments()
        redmine_issue.save()
        add_comments()

        delete_folder()
        issues_dict[issue_id] = redmine_issue.id

    print "\n==========Setting issue relations and time tracking=========="
    for yt_issue, rdmn_issue in issues_dict.items():
        print 'YT issue: ' + str(yt_issue) + ' Redmine issue: ' + str(rdmn_issue)
        set_parents()
        set_relates()
        set_depends()
        set_duplicates()
        add_tracking()

    execution_time = time.time() - start_time
    print "==========Migration completed.=========="
    print("--- %s seconds ---" % str(execution_time))
