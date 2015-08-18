#!/usr/bin/env python
# coding: utf-8

import ansible.utils.pybook as pybook
# :TRICKY: доступ к функционалу, идентичный для Pybooks
globals().update(pybook.book_globals)
import logging

log_installing_packages = False

def install_packages(name, lst):
    if log_installing_packages:
        logging.warn("Installing packages: %s" % ' '.join(lst))
        
    with mapping:
        append("name", name)
        append("apt",  "pkg={{ item }} state=present")
        with sequence("with_items"):
            for item in lst:
                append(item)

def make_base_tasks():
    install_packages("install common admin tools", [
        "tmux",
        "vim",
        "less",
        "locales", # locale-gen
        "sudo",    # Ansible, become_user
    ])
    
    with mapping:
        append("name",    "gen ru_RU.utf8 locale for reading code comments")
        append("command", "locale-gen ru_RU.utf8")
        # :KLUDGE: лучший вариант - создать дополнительно файл и проверять его с creates:
        # locale-gen ru_RU.utf8 && touch /opt/gen_ru_RU.utf8 (но так проще)
        append("changed_when", False)

        # :KLUDGE: в Debian 7/Wheezy locale-gen не принимает аргументы, а генерирует
        # локали из списка /etc/locale.gen; в итоге, чтобы сгенерировать локали, придется вручную (без Ansible):
        # - dpkg-reconfigure locales
        # - ввести числа 138, 349 через пробел (это есть en_US.utf8, ru_RU.utf8)
        # - выбрать локаль по умолчанию, одну из этих (пропишется в /etc/default/locale)
        append("when", "ansible_distribution_release != 'wheezy'")
        
    with when("ansible_distribution_release == 'wheezy'"):
        with mapping:
            append("lineinfile", """dest=/etc/locale.gen line='en_US.UTF-8 UTF-8' """)

        # пока у меня есть в LC_* и LANG обе локали, их нужно иметь и на целевой машине,
        # иначе часть прог ломается (less ломается всегда, python-проги - из-за LANG)
        with mapping:
            append("lineinfile", """dest=/etc/locale.gen line='ru_RU.UTF-8 UTF-8' """)
            
        with mapping:
            append("name",    "regen added locales")
            append("command", "locale-gen")
            append("changed_when", False)

# лучше, чтоб в cmd и cwd не было никаких кавычек
def run_host_cmd(title, cmd, cwd, condition):
    with mapping:
        append("name", title)
        # :TRICKY: полный отстой - дополнительно в кавычки приходится ставить переменные, "{{}}",
        # если есть знаки равно; причем для модуля command это не требуется - /bin/true {{}}
        # :REFACTOR:
        append("debug", '''msg=run_host_cmd-ok "{{ '%(cmd)s' | system(cwd='%(cwd)s', cache=True) }}"''' % locals())
        append("when", condition)
            
def install_mysql_server():
    install_packages("install mysql", [
        "mysql-server",
        "python-mysqldb", # для модулей Ansible
    ])
    
    
import contextlib
@contextlib.contextmanager
def db_not_exists(dbname):
    with mapping:
        append("name",    "check %(dbname)s db existance" % locals())
        append("command", """mysql -sNe "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME='%(dbname)s'" """ % locals())
        append("register", "%(dbname)s_existance_out" % locals())
        append("changed_when", False)
        
    with when("""%(dbname)s_existance_out.stdout.find('%(dbname)s') == -1""" % locals()):
        yield None

#
# supervisor
#

def notify_supervisor_restart():
    with sequence("notify"):
        append("restart supervisor")

def setup_supervisor_daemon(name, template):
    # первей установка, потому что иначе
    # /etc/supervisor/conf.d нет
    install_packages("install supervisor", [
        "supervisor",
    ])
    
    # supervisor
    with mapping:
        append("template", "src=%(template)s dest=/etc/supervisor/conf.d/%(name)s.conf" % locals())
        notify_supervisor_restart()
    

def restart_supervisor():
    with mapping:
        append("name", "restart supervisor")
        append("service", "name=supervisor state=restarted")


def unarchive_if_not_exists(title, dst_dir, src, user):
    reg_name = "stat_%s" % id(dst_dir)
    with mapping:
        append("name",    "check %(title)s exists" % locals())
        append("stat", """path=%(dst_dir)s""" % locals())
        append("register", reg_name)
    
    with when("""not %(reg_name)s.stat.exists""" % locals()):
        # :TRICKY: не всегда у пользователя есть одноименная группа
        # кроме тогда, group=root заведомо неплохой выбор в плане безопасности
        # 
        #acl = "owner=%(user)s group=%(user)s" % locals()
        acl = "owner=%(user)s" % locals()
        with mapping:
            append("file", "path=%(dst_dir)s %(acl)s state=directory" % locals())
        
        with mapping:
            append("unarchive", "src=%(src)s dest=%(dst_dir)s %(acl)s" % locals())
