#!/usr/bin/env python

##########################################################################
#                                                                        #
#  This program is free software; you can redistribute it and/or modify  #
#  it under the terms of the GNU General Public License as published by  #
#  the Free Software Foundation; version 2 of the License.               #
#                                                                        #
#  This program is distributed in the hope that it will be useful,       #
#  but WITHOUT ANY WARRANTY; without even the implied warranty of        #
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the         #
#  GNU General Public License for more details.                          #
#                                                                        #
##########################################################################

## etree
from lxml import etree

from bz2 import BZ2File
import sys
#import cProfile as profile
from functools import partial
import logging
import re
from collections import defaultdict

## multiprocessing
from multiprocessing import Pipe, Process

from sonet.graph import load as sg_load
from sonet import lib
import sonet.mediawiki as mwlib

## nltk
import nltk



count_utp, count_missing = 0, 0
lang_user, lang_user_talk = None, None
tag = {}
en_user, en_user_talk = u"User", u"User talk"
user_classes = None

## frequency distribution

logging.basicConfig(stream=sys.stderr, level=logging.DEBUG)

### CHILD PROCESS

# smile dictionary
dsmile = {
    'happy': (r':[ -]?[)\]>]', r'=[)\]>]', r'\^[_\- .]?\^', 'x\)', r'\(^_^\)'),
    'sad': (r':[\- ]?[(\[<]', r'=[(\[<]'),
    'laugh': (r':[ -]?D', '=D'),
}

## r argument is just for caching
def remove_templates(text, r=re.compile(r"{{.*?}}")):
    """
    Remove Mediawiki templates from given text:

    >>> remove_templates("hello{{template}} world")
    'hello world'
    >>> remove_templates("hello{{template}} world{{template2}}")
    'hello world'
    """
    return r.sub("", text)

## dsmile argument is just for caching
def find_smiles(text, dsmile=dsmile):
    """
    Find smiles in text and returns a dictionary of found smiles

    >>> find_smiles(':) ^^')
    {'happy': 2}
    >>> find_smiles('^^')
    {'happy': 1}
    """
    res = {}
    for name, lsmile in dsmile.iteritems():
        regex_smile = '(?:%s)' % ('|'.join(lsmile))
        res[name] = len([1 for match in re.findall(regex_smile, text)
                         if match])

    return dict(res)

def get_freq_dist(recv, send, fd=None, dcount_smile=None, classes=None):
    """
    Find word frequency distribution and count smile in the given text.

    Parameters
    ----------
    recv : multiprocessing.Connection
        Read only
    send : multiprocessing.Connection
        Write only
    fd : dict
        Word frequency distributions
    dcount_smile : dict
        Smile counters
    """
    from operator import itemgetter
    stopwords = frozenset(
        nltk.corpus.stopwords.words('italian')
        ).union(
            frozenset("[]':,(){}.?!*\"")
        ).union(
            frozenset(("==", "--"))
        )
    tokenizer = nltk.PunktWordTokenizer()

    if not classes:
        classes = ('anonymous', 'bot', 'bureaucrat', 'sysop', 'normal user',
                   'all')

    # prepare a dict of empty FreqDist, one for every class
    if not fd:
        fd = dict([(cls, nltk.FreqDist()) for cls in classes])
    if not dcount_smile:
        dcount_smile = dict([(cls, {}) for cls in classes])

    while 1:
        try:
            cls, msg = recv.recv()
        except TypeError: ## end
            send.send([(cls, sorted(freq.items(),
                                    key=itemgetter(1),
                                    reverse=True)[:1000])
                       for cls, freq in fd.iteritems()])
            send.send([(cls, sorted(counters.items(),
                                    key=itemgetter(1),
                                    reverse=True))
                       for cls, counters in dcount_smile.iteritems()])

            return

        msg = remove_templates(msg)

        ## TODO: update 'all' just before sending by summing the other fields
        count_smile = find_smiles(msg)
        dcount_smile[cls].update(count_smile)
        dcount_smile['all'].update(count_smile)

        tokens = tokenizer.tokenize(nltk.clean_html(msg.encode('utf-8')
                                                        .lower()))

        text = nltk.Text(t for t in tokens if t not in stopwords)
        fd[cls].update(text)
        fd['all'].update(text)


#def get_freq_dist_wrapper(q, done_q, fd=None):
#    profile.runctx("get_freq_dist(q, done_q, fd)",
#        globals(), locals(), 'profile')


### MAIN PROCESS
def process_page(elem, send):
    """
    send is a Pipe connection, write only
    """
    user = None
    global count_utp, count_missing

    for child in elem:
        if child.tag == tag['title'] and child.text:
            a_title = child.text.split('/')[0].split(':')

            try:
                if a_title[0] in (en_user_talk, lang_user_talk):
                    user = a_title[1]
                else:
                    return
            except KeyError:
                return
        elif child.tag == tag['revision']:
            for rc in child:
                if rc.tag != tag['text']:
                    continue

                #assert user, "User still not defined"
                if not (rc.text and user):
                    continue

                user = user.encode('utf-8')
                try:
                    send.send((user_classes[user], rc.text))
                except:
                    ## fix for anonymous users not in the rich file
                    if mwlib.isip(user):
                        send.send(('anonymous', rc.text))
                    else:
                        logging.warn("Exception with user %s" % (user,))
                        count_missing += 1

                count_utp += 1

                if not count_utp % 500:
                    print >> sys.stderr, count_utp


def main():
    import optparse

    p = optparse.OptionParser(
        usage="usage: %prog [options] dump enriched_pickle"
    )

    _, args = p.parse_args()

    if len(args) != 2:
        p.error("Too few or too many arguments")
    xml, rich_fn = args

    global lang_user_talk, lang_user, tag, user_classes
    ## pipe to send data to the  subprocess
    p_receiver, p_sender = Pipe(duplex=False)
    ## pipe to get elaborated data from the subprocess
    done_p_receiver, done_p_sender = Pipe(duplex=False)

    src = BZ2File(xml)

    tag = mwlib.getTags(src)
    lang, date, _ = mwlib.explode_dump_filename(xml)
    user_classes = dict(sg_load(rich_fn).get_user_class('username',
                                  ('anonymous', 'bot', 'bureaucrat','sysop')))

    p = Process(target=get_freq_dist, args=(p_receiver, done_p_sender))
    p.start()

    translations = mwlib.getTranslations(src)
    lang_user, lang_user_talk = translations['User'], translations['User talk']

    assert lang_user, "User namespace not found"
    assert lang_user_talk, "User Talk namespace not found"

    ## open with a faster decompressor (probably this cannot seek)
    src.close()
    src = lib.BZ2FileExt(xml)

    partial_process_page = partial(process_page, send=p_sender)
    mwlib.fast_iter(etree.iterparse(src, tag=tag['page']),
                    partial_process_page)
    logging.info('Users missing in the rich file: %d' % (count_missing,))

    p_sender.send(0) ## this STOPS the process

    print >> sys.stderr, "end of parsing"

    # get a list of pair (class name, frequency distributions)
    for cls, fd in done_p_receiver.recv():
        with open("%swiki-%s-words-%s.dat" %
                  (lang, date,
                   cls.replace(' ', '_')), 'w') as out:
            for k, v in fd:
                print >> out, v, k
    del fd

    for cls, counters in done_p_receiver.recv():
        with open("%swiki-%s-smile-%s.dat" %
                  (lang, date,
                   cls.replace(' ', '_')), 'w') as out:
            for k, v in counters:
                print >> out, v, k

    p.join()

    print >> sys.stderr, "end of FreqDist"


if __name__ == "__main__":
    #import cProfile as profile
    #profile.run('main()', 'mainprof')
    main()