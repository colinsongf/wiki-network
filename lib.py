import os
import sys
import csv


def find_executable(executable, path=None):
    """Try to find 'executable' in the directories listed in 'path' (a
    string listing directories separated by 'os.pathsep'; defaults to
    os.environ['PATH']).  Returns the complete filename or None if not
    found
    """
    if path is None:
        path = os.environ['PATH']
    paths = path.split(os.pathsep)
    extlist = ['']
    if os.name == 'os2':
        (base, ext) = os.path.splitext(executable)
        # executable files on OS/2 can have an arbitrary extension, but
        # .exe is automatically appended if no dot is present in the name
        if not ext:
            executable = executable + ".exe"
    elif sys.platform == 'win32':
        pathext = os.environ['PATHEXT'].lower().split(os.pathsep)
        (base, ext) = os.path.splitext(executable)
        if ext.lower() not in pathext:
            extlist = pathext
    for ext in extlist:
        execname = executable + ext
        if os.path.isfile(execname):
            return execname
        else:
            for p in paths:
                f = os.path.join(p, execname)
                if os.path.isfile(f):
                    return f
    else:
        return None


def BZ2FileExt(fn):
    from subprocess import Popen, PIPE

    executable = 'lbzip2' if find_executable('lbzip2') else 'bzip2'

    unzip_process = Popen([executable, '-c', '-k', '-d', fn], stdout=PIPE)

    return unzip_process.stdout


def SevenZipFileExt(fn, lines=None):
    """
    fn: filename
    lines: if you don't want the whole file, specify how many lines you want
    """
    from subprocess import Popen, PIPE

    if not find_executable('7z'):
        raise Exception, 'Cannot find 7zip executable (7z)'

    unzip_process = Popen(['7z', 'e', '-so', fn], stdout=PIPE, stderr=PIPE)
    stdout = unzip_process.stdout

    if not lines:
        return stdout
    else:
        import mmap
        m = mmap.mmap(-1, 16*1024)
        for i in xrange(lines):
            line = stdout.readline()
            if not line: break
            m.write(line)
        m.seek(0)
        return m


def ensure_dir(f):
    d = os.path.dirname(f)
    if not os.path.exists(d):
        print 'creating dir: %s' % (d,)
        os.makedirs(d)


def print_csv(d, filename, header=None, delimiter=","):

    print "Writing filename %s" % (filename,)

    try:
        with open(filename, 'w') as f:
            wr = csv.writer(f, delimiter=delimiter)

            if header is not None:
                wr.writerow(header)
            for k, v in d.iteritems():
                ls = []
                if header is not None:
                    for h in header:
                        if h in v.keys():
                            ls.append(v[h])
                        else:
                            ls.append(None)
                    wr.writerow(ls)
                else:
                    wr.writerow(v.values())
    except IOError, e:
        print e

    print "File %s saved" % (filename,)


def iter_csv(filename, _hasHeader = False):
    from csv import reader
    fieldNames = None

    print 'Reading from %s' % (filename,)

    try:
        cf = open(filename, 'rb')
    except IOError, e:
        print e

    try:
        lines = reader(cf)
    except IOError, e:
        print e[0], e[1]

    if _hasHeader:
        fieldNames = lines.next()

    for row in lines:
        d = {}
        for i, f in enumerate(row):
            if fieldNames:
                d[fieldNames[i]] = f
            else:
                d[i] = f
        yield d

    cf.close()
