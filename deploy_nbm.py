#!/usr/bin/env python
""" Helper script to update SNAP update center with new NBMs

This code is released under GPL-3 or any later version.
"""

import os
import shutil
import sys
import argparse
import datetime
import logging
import zipfile
from lxml import etree
import StringIO
import gzip
from distutils.version import LooseVersion

__author__ = "Julien Malik"
__copyright__ = "Copyright 2015, CS-SI"
__credits__ = ["Julien Malik", "Marco Peters"]
__license__ = "GPL"
__version__ = "1.0"
__maintainer__ = "Julien Malik"
__email__ = "julien.malik@c-s.fr"
__status__ = "Production"

UPDATECENTER_ROOT="/var/www/updatecenter"

def is_nbm(path):
  # TODO : add more sanity checks to avoid corrupted nbms
  return os.path.isfile(path) and os.path.splitext(path)[1] == ".nbm"

def check_nbm_dir(nbmdir):
  if not os.path.isdir(nbmdir):
    raise argparse.ArgumentTypeError("%s is not a directory" % nbmdir)
  nbms = [f for f in os.listdir(nbmdir) if is_nbm(os.path.join(nbmdir, f))]
  if not nbms:
    raise argparse.ArgumentTypeError("%s does not contain any nbm file" % nbmdir)
  return nbmdir
  
def setup_logging():
  logging.basicConfig(format='%(asctime)s - %(levelname)s: %(message)s', level=logging.DEBUG)
  
def check_permissions():
  # TODO : need to be root
  pass

def check_input(args):
  if args.nbmdir is None:
      raise argparse.ArgumentTypeError("Missing [nbmdir] argument")

def duplicate_current(args):
  now = datetime.datetime.now()
  nowstr = '{0:%Y%m%d-%H%M%S}'.format(now)
  old_updatecenter=os.path.realpath(os.path.join(UPDATECENTER_ROOT,args.release))
  new_updatecenter='{uc}_{nowstr}'.format(uc=os.path.join(UPDATECENTER_ROOT, args.release), nowstr=nowstr)
  logging.info('Creating %s' % new_updatecenter)
  shutil.copytree(old_updatecenter, new_updatecenter)
  return os.path.basename(new_updatecenter)

def get_codenamebase(nbm):
  f = zipfile.ZipFile(nbm)
  with f.open('Info/info.xml') as info:
    root = etree.parse( info ).getroot()
    return root.get('codenamebase')

def get_specification_version(nbm):
  f = zipfile.ZipFile(nbm)
  with f.open('Info/info.xml') as info:
    root = etree.parse( info ).getroot()
  children = list(root)
  for child in children:
    if child.tag == 'manifest':
      return LooseVersion(child.get('OpenIDE-Module-Specification-Version'))
  raise RuntimeError('Unable to get OpenIDE-Module-Specification-Version from %s' % nbm)

def deploy_nbms(args, uc):
  nbms_todeploy = [f for f in os.listdir(args.nbmdir) if is_nbm(os.path.join(args.nbmdir, f))]
  codename_todeploy = [get_codenamebase(os.path.join(args.nbmdir,nbm)) for nbm in nbms_todeploy]

  repo = os.path.join(UPDATECENTER_ROOT, uc, args.repo)
  current_nbms = [f for f in os.listdir(repo) if is_nbm(os.path.join(repo, f))]
  nbms_todelete = [nbm for nbm in current_nbms if get_codenamebase(os.path.join(repo,nbm)) in codename_todeploy]
  for nbm_todelete in nbms_todelete:
    nbm_todelete_path = os.path.join(repo,nbm_todelete)
    for nbm_todeploy in nbms_todeploy:
      nbm_todeploy_path = os.path.join(args.nbmdir,nbm_todeploy)
      if get_codenamebase(nbm_todeploy_path) == get_codenamebase(nbm_todelete_path):
        version_todeploy = get_specification_version(nbm_todeploy_path)
        version_todelete = get_specification_version(nbm_todelete_path)
        if version_todeploy > version_todelete:
          logging.warning('Deleting {0} (was version {1}, superseeded by {2} with version {3})'\
            .format(nbm_todelete, version_todelete, nbm_todeploy, version_todeploy))
        else:
          message = 'You want to deploy {0} with specification version {1}, but there is already {2} with version {3} in the repository'\
            .format(nbm_todeploy, version_todeploy, nbm_todelete, version_todelete)
          logging.error(message)
          raise RuntimeError(message)
  
  for nbm in nbms_todeploy:
    logging.info('Deploying %s (codename : %s)' % (nbm, get_codenamebase(os.path.join(args.nbmdir,nbm))))

  for nbm_todelete in nbms_todelete:
    nbm_todelete_path = os.path.join(repo,nbm_todelete)
    os.remove(nbm_todelete_path)
    
  for nbm_todeploy in nbms_todeploy:
    nbm_todeploy_input_path = os.path.join(args.nbmdir,nbm_todeploy)
    nbm_todeploy_output_path = os.path.join(repo,nbm_todeploy)
    shutil.copy(nbm_todeploy_input_path, nbm_todeploy_output_path)

def get_module_info(nbm):
  f = zipfile.ZipFile(nbm)
  with f.open('Info/info.xml') as info:
    root = etree.parse( info ).getroot()
    
    children = list(root)
    license = None
    for child in children :
      if child.tag == 'license':
        license = child
    if license is not None:
      del root[root.index(license)]
    
    root.set('downloadsize', str(os.path.getsize(nbm)))
    return (root, license)

def get_dtd():
  # content of http://www.netbeans.org/dtds/autoupdate-catalog-2_5.dtd
  dtdstr = """
<!-- -//NetBeans//DTD Autoupdate Catalog 2.5//EN -->
<!-- XML representation of Autoupdate Modules/Updates Catalog -->

<!ELEMENT module_updates ((notification?, (module_group|module)*, license*)|error)>
<!ATTLIST module_updates timestamp CDATA #REQUIRED>

<!ELEMENT module_group ((module_group|module)*)>
<!ATTLIST module_group name CDATA #REQUIRED>

<!ELEMENT notification (#PCDATA)>
<!ATTLIST notification url CDATA #IMPLIED>

<!ELEMENT module (description?, module_notification?, external_package*, (manifest | l10n) )>
<!ATTLIST module codenamebase CDATA #REQUIRED
                 homepage     CDATA #IMPLIED
                 distribution CDATA #REQUIRED
                 license      CDATA #IMPLIED
                 downloadsize CDATA #REQUIRED
                 needsrestart (true|false) #IMPLIED
                 moduleauthor CDATA #IMPLIED
                 releasedate  CDATA #IMPLIED
                 global       (true|false) #IMPLIED
                 targetcluster CDATA #IMPLIED
                 eager (true|false) #IMPLIED
                 autoload (true|false) #IMPLIED>

<!ELEMENT description (#PCDATA)>

<!ELEMENT module_notification (#PCDATA)>

<!ELEMENT external_package EMPTY>
<!ATTLIST external_package
                 name CDATA #REQUIRED
                 target_name  CDATA #REQUIRED
                 start_url    CDATA #REQUIRED
                 description  CDATA #IMPLIED>

<!ELEMENT manifest EMPTY>
<!ATTLIST manifest OpenIDE-Module CDATA #REQUIRED
                   OpenIDE-Module-Name CDATA #REQUIRED
                   OpenIDE-Module-Specification-Version CDATA #REQUIRED
                   OpenIDE-Module-Implementation-Version CDATA #IMPLIED
                   OpenIDE-Module-Module-Dependencies CDATA #IMPLIED
                   OpenIDE-Module-Package-Dependencies CDATA #IMPLIED
                   OpenIDE-Module-Java-Dependencies CDATA #IMPLIED
                   OpenIDE-Module-IDE-Dependencies CDATA #IMPLIED
                   OpenIDE-Module-Short-Description CDATA #IMPLIED
                   OpenIDE-Module-Long-Description CDATA #IMPLIED
                   OpenIDE-Module-Display-Category CDATA #IMPLIED
                   OpenIDE-Module-Provides CDATA #IMPLIED
                   OpenIDE-Module-Requires CDATA #IMPLIED
                   OpenIDE-Module-Recommends CDATA #IMPLIED
                   OpenIDE-Module-Needs CDATA #IMPLIED
                   AutoUpdate-Show-In-Client (true|false) #IMPLIED
                   AutoUpdate-Essential-Module (true|false) #IMPLIED>

<!ELEMENT l10n EMPTY>
<!ATTLIST l10n   langcode             CDATA #IMPLIED
                 brandingcode         CDATA #IMPLIED
                 module_spec_version  CDATA #IMPLIED
                 module_major_version CDATA #IMPLIED
                 OpenIDE-Module-Name  CDATA #IMPLIED
                 OpenIDE-Module-Long-Description CDATA #IMPLIED>

<!ELEMENT license (#PCDATA)>
<!ATTLIST license name CDATA #REQUIRED>
"""
  dtdio = StringIO.StringIO(dtdstr)
  dtd = etree.DTD(dtdio)
  dtdio.close()    
  return dtd

def generate_updatexml(args, uc):
  repo = os.path.join(UPDATECENTER_ROOT, uc, args.repo)
  nbms = [f for f in os.listdir(repo) if is_nbm(os.path.join(repo, f))]
  
  licenses = set()
  module_updates = etree.Element('module_updates', timestamp = '{0:%S/%M/%H/%d/%m/%Y}'.format(datetime.datetime.now()))
  
  if args.notif is not None:
    notification = etree.Element('notification')
    notification.text = args.notif
    if args.notifurl is not None:
      notification.set('url', args.notifurl)
    module_updates.append(notification)
  
  for nbm in nbms:
    nbm_path = os.path.join(repo, nbm)
    (root, license) = get_module_info(nbm_path)
    module_updates.append( root )
    if license is not None:
      # add this license, if not already done
      if {lic for lic in licenses if lic.get('name')  == license.get('name')} == set() :
        licenses.add( license )

  if len(licenses) > 1:
    logging.warn('Modules have %d different licenses' % len(licenses))
  for license in licenses:
    module_updates.append( license )

  with open( os.path.join(repo, 'updates.xml'), 'w' ) as updates_file :
    updates_file.write( etree.tostring(module_updates, pretty_print=True, encoding="UTF-8", xml_declaration=True, doctype='<!DOCTYPE module_updates PUBLIC "-//NetBeans//DTD Autoupdate Catalog 2.5//EN" "http://www.netbeans.org/dtds/autoupdate-catalog-2_5.dtd">') )
  
  # validate DTD
  dtd = get_dtd()
  with open( os.path.join(repo, 'updates.xml'), 'r' ) as updates_file :
    if not dtd.validate(etree.parse(updates_file)):
      message = 'Generated updates.xml does not validate DTD !'
      logging.error(message)
      raise RuntimeError(message)
    else:
      logging.info('Generated updates.xml validates DTD successfully')

  # gz
  with open(os.path.join(repo, 'updates.xml'), 'rb') as f_in, \
       gzip.open(os.path.join(repo, 'updates.xml.gz'), 'wb') as f_out:
    shutil.copyfileobj(f_in, f_out)

def update_symlink(args, uc):
  os.system('cd {0} && ln -nsf {1} {2}'.format(UPDATECENTER_ROOT, uc, args.release))

def main():
  parser = argparse.ArgumentParser(prog='deploy_nbm.py', description='Deploy nbms to the Update Center')
  parser.add_argument('nbmdir', nargs='?', help='The directory containing the new nbm files to deploy', type=check_nbm_dir)
  parser.add_argument('--repo', nargs='?', help='The repository to deploy to', \
    choices=['snap', 'snap-extensions', 'snap-community'], required=True)
  parser.add_argument('--release', nargs='?', help='The major SNAP release', \
    choices=['2.0'], default='2.0')
  parser.add_argument('--notif', nargs='?', help='The notification message')
  parser.add_argument('--notifurl', nargs='?', help='The notification url (only used if --notif is provided)')
  args = parser.parse_args()
  
  setup_logging()
  check_permissions()
  check_input(args)
  uc = duplicate_current(args)
  deploy_nbms(args, uc)
  generate_updatexml(args, uc)
  update_symlink(args, uc)
  
  
if __name__=="__main__":
  main()
