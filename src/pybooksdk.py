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
        #append("apt",  "pkg={{ item }} state=present")
        #with sequence("with_items"):
            #for item in lst:
                #append(item)
        with mapping("apt"):
            with sequence("pkg"):
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
        #append("when", "ansible_distribution_release != 'wheezy'")
        append("when", "ansible_distribution != 'Debian'")

    with when("ansible_distribution == 'Debian'"):
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
def work_not_done(title, cmd, obj_name, var_suffix, condition):
    var_name = obj_name.replace("-", "_")
    var_name = "%(var_name)s_%(var_suffix)s" % locals()

    with mapping:
        append("name",    title)
        append("command", cmd)
        append("register", var_name)
        append("changed_when", False)
        append("failed_when", False)

    with when("""%(var_name)s.%(condition)s""" % locals()):
        yield None


def db_not_exists(dbname):
    return work_not_done(
        "check %(dbname)s db existance" % locals(),
        """mysql -sNe "SELECT SCHEMA_NAME FROM INFORMATION_SCHEMA.SCHEMATA WHERE SCHEMA_NAME='%(dbname)s'" """ % locals(),
        dbname,
        "existance_out",
        "stdout.find('%(dbname)s') == -1" % locals()
    )

def package_not_installed(pkg_name):
    return work_not_done(
        "check if %(pkg_name)s is installed" % locals(),
        """dpkg-query -l %(pkg_name)s""" % locals(),
        pkg_name,
        "apt_installed",
        "rc != 0"
    )

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

    # если C-локаль, запускаемые (Python3-)проги не читают текстовые файлы как Unicode-ные, и т.д.
    # :TRICKY: работает и без export, но только если переменная LANG уже в окружении => поэтому export
    with mapping:
        append("lineinfile", """dest=/etc/default/supervisor regexp="LANG.*=" line="export LANG=en_US.utf8" """)

    # supervisor
    with mapping:
        append("template", "src=%(template)s dest=/etc/supervisor/conf.d/%(name)s.conf" % locals())
        notify_supervisor_restart()


def restart_supervisor(sleep=None):
    with mapping:
        append("name", "restart supervisor")
        if sleep is None:
            # Ошибка "restart supervisor" => failed
            # на 3х сервисах (сферических, в вакууме):
            # (эмпирически) 2 секунд не хватает всегда
            # 3-х - на тестовых всегда хватает
            #pybooksdk.restart_supervisor(3)

            # kill -HUP - самый адекватный способ перезагружать supervisor,
            # потому что только он знает, сколько времени можно разрешать
            # работать своим процессам
            # Аналогично, "supervisorctl shutdown", kill -TERM pid - самый адекватные способы
            # прекращать работу supervisor-а (второе делает системный скрипт с помощью start-stop-daemon,
            # а вот перезагрузку не умеет)
            append("shell", "kill -HUP `supervisorctl pid`")
        else:
            # устаревший режим, если вдруг kill -HUP ошибку будет выдавать или еще чего
            append("service", "name=supervisor state=restarted sleep=%(sleep)s" % locals())

@contextlib.contextmanager
def if_not_exists(title, dst_path):
    reg_name = "stat_%s" % id(dst_path)
    with mapping:
        append("name",    "check %(title)s exists" % locals())
        append("stat", """path=%(dst_path)s""" % locals())
        append("register", reg_name)

    with when("""not %(reg_name)s.stat.exists""" % locals()):
        yield None

def unarchive_if_not_exists(title, dst_dir, src, user):
    with if_not_exists(title, dst_dir):
        # :TRICKY: не всегда у пользователя есть одноименная группа
        # кроме тогда, group=root заведомо неплохой выбор в плане безопасности
        #
        #acl = "owner=%(user)s group=%(user)s" % locals()
        acl = "owner=%(user)s" % locals()
        with mapping:
            append("file", "path=%(dst_dir)s %(acl)s state=directory" % locals())

        with mapping:
            append("unarchive", "src=%(src)s dest=%(dst_dir)s %(acl)s" % locals())
