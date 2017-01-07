"""
Copyright (c) 2016 Hailin Su

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import socket
import select
import sys
import getpass
import re
import time
import threading
from collections import deque

" A telnet client connecting to play.slashdiablo.net:6112 "


class D2BNClient:
    def __init__(self, host, port, user):
        self.host = host
        self.port = port
        self.user = user
        self.sock = socket
        self.chat_only = True
        # self.pattern_here = re.compile(r'^\[.* is here\].*\[.* is here\]$', re.DOTALL)
        self.pattern_entr = re.compile(r'^\[.* enters\].$', re.DOTALL)
        self.pattern_leav = re.compile(r'^\[.* leaves\].$', re.DOTALL)

    def connect(self):
        print("Before connect to [ {} : {} ], please input password for {}".format(self.host, self.port, self.user))
        pswd = getpass.getpass()
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(2)
            self.sock.connect((self.host, self.port))
        except socket.gaierror:
            print('Unable to connect')
            return False

        print(' [+] Connected to remote host')

        self.sock.send(b'\r')
        self.sock.recv(128)
        data = self.user + "\n"
        self.sock.send(data.encode('ascii'))
        self.sock.recv(128)
        data = pswd + "\n"
        self.sock.send(data.encode('ascii'))
        self.sock.recv(128)
        try:
            self.sock.recv(128)
            self.sock.recv(1024)
        except socket.timeout:
            pass

        self.ch_channel()

        done = False
        while not done:
            socket_list = [sys.stdin, self.sock]

            # Get the list sockets which are readable
            read_sockets, write_sockets, error_sockets = select.select(socket_list, [], [])

            for sock in read_sockets:
                # incoming message from remote server
                if sock == self.sock:
                    data = sock.recv(4096)
                    if not data:
                        self.log('Connection closed')
                        # sys.exit()
                        done = True
                    else:
                        # print data
                        for msg in data.decode('ascii').split('\n'):
                            if self.filter_in(msg) and len(msg):
                                self.log(msg)

                # user entered a message
                else:
                    msg = sys.stdin.readline()
                    if self.process_command(msg):
                        self.sock.send(msg.encode('ascii'))
        self.finalize()

    def finalize(self):
        self.sock.close()

    def log(self, msg):
        print("[{}] {} | {}".format(self.user, time.strftime("%H:%M:%S"), msg))

    def ch_channel(self):
        """ to be overridden """
        data = "/join diablo ii-1\n"
        self.sock.send(data.encode('ascii'))

    def filter_in(self, data):
        """
        :param data: str data
        :return: if chat_only defined true, filter out [] contents and return false so that it will not get printed
        """
        ret = True
        if self.chat_only:
            if self.pattern_entr.match(data) or self.pattern_leav.match(data):  # or self.pattern_here.match(data)
                ret = False
        return ret

    def process_command(self, msg):
        """
        Pre process command before send as bnet message
        :param msg: str from stdin
        :return: True if pass on to send as bnet message
        """
        return True


" A log watcher based on telnet client connecting to play.slashdiablo.net:6112 "


class D2BNLogger(D2BNClient):
    def __init__(self, host, port, user):
        super(D2BNLogger, self).__init__(host, port, user)
        self.ofs = open("log.D2BNLogger", "a")

    def ch_channel(self):
        """
        change channel to d2bnlogger
        :return:
        """
        data = "/join D2BNLogger\n"
        self.sock.send(data.encode('ascii'))
        self.log("joined channel D2BNLogger")
        done = False
        while not done:
            try:
                self.sock.recv(1024)
            except socket.timeout:
                done = True

        data = "/watchall\n"
        self.sock.send(data.encode('ascii'))

    def log(self, msg):
        self.ofs.write("{} {}\n".format(time.strftime("%H:%M:%S |"), msg))
        self.ofs.flush()
        super(D2BNLogger, self).log(msg)

    def finalize(self):
        self.ofs.close()
        super(D2BNLogger, self).finalize()

" An implementation of infobot based on telnet client connecting to play.slashdiablo.net:6112 "


class D2InfoBot(D2BNLogger, threading.Thread):
    def __init__(self, host, port, user):
        super(D2InfoBot, self).__init__(host, port, user)
        threading.Thread.__init__(self)
        self.bot = infobot()
        # create cmd patterns
        self.map_cmd2ptn = {}
        self.ptn_whisper = re.compile(r"^<from (.{2,16})> (.*)")
        self.ptn_general = re.compile(r"^<(.{2,16})>.*" + self.user + r".*", re.IGNORECASE)
        self.vec_cmd = deque()
        self.stop = False
        self.start()

    def run(self):
        while not self.stop:
            if len(self.vec_cmd):
                line = self.vec_cmd.popleft()
                frm = self.ptn_whisper.search(line).group(1)
                reply = self.bot.get_info(line)
                for ln in reply.split("\n"):
                    self.sock.send(("/m " + frm + " " + ln + "\n").encode('ascii'))
            else:
                time.sleep(1)

    def ch_channel(self):
        """ stay in chat! not change to anywhere! """
        pass

    def filter_in(self, data):
        """
        override: added process commands
        :param data: str data, a line without ending \n
        :return: if chat_only defined true, filter out [] contents and return false so that it will not get printed
        """
        cmd = data.strip()
        rs = self.ptn_whisper.search(cmd)
        if rs:
            self.vec_cmd.append(cmd)
        else:
            rs = self.ptn_general.search(cmd)
            if rs:
                frm = rs.group(1)
                reply = "/m {} Hi {}, I'm an unofficially and partially implemented InfoBot.".format(frm, frm)\
                        + " Whisper me something to see how it works.\n"
                print(reply, end="")
                self.sock.send(reply.encode('ascii'))

        return super(D2InfoBot, self).filter_in(data)

    def finalize(self):
        self.stop = True
        super(D2InfoBot, self).finalize()


class infobot:
    def __init__(self):
        self.pattern = re.compile(r"^<from .{2,16}> (.*)")
        self.map_fullcmd2ret = {
            "help":     "valid commands: help bp rw(low only)",
            "help bp":  "bp (fcr|fhr) (ama|sin|zon|sor|pal|bar|dru|asn)",
            "help rw":  "rw (rune|#), example: rw ort, rw 9",
            "rw":       "rune el(1) tir(3) nef(4) eth(5) tal(7) ral(8) ort(9) thul(10) amn(11) sol(12) shael(13)",
            "rw el":    "Steel tir(3) el(1)",
            "rw 1":     "Steel tir(3) el(1)",
            "rw tir":   "Steel tir(3) el(1), "
                        + "Leaf tir(3) ral(8), "
                        + "Strength amn(11) tir(3), "
                        + "Insight ral(8) tir(3) tal(7) sol(12)",
            "rw 3":     "Steel tir(3) el(1), "
                        + "Leaf tir(3) ral(8), "
                        + "Strength amn(11) tir(3), "
                        + "Insight ral(8) tir(3) tal(7) sol(12)",
            "rw nef":   "Smoke nef(4) lum(17)",
            "rw 4":     "Smoke nef(4) lum(17)",
            "rw eth":   "Stealth tal(7) eth(5), "
                        + "Rhyme shael(13) eth(5), "
                        + "Splendor eth(5) lum(17)",
            "rw 5":     "Stealth tal(7) eth(5), "
                        + "Rhyme shael(13) eth(5), "
                        + "Splendor eth(5) lum(17)",
            "rw tal":   "Stealth tal(7) eth(5), "
                        + "Ancient's Pledge ral(8) ort(9) tal(7), "
                        + "Spirit tal(7) thul(10) ort(9) amn(11), "
                        + "Insight ral(8) tir(3) tal(7) sol(12)",
            "rw 7":     "Stealth tal(7) eth(5), "
                        + "Ancient's Pledge ral(8) ort(9) tal(7), "
                        + "Spirit tal(7) thul(10) ort(9) amn(11), "
                        + "Insight ral(8) tir(3) tal(7) sol(12)",
            "rw ral":   "Leaf tir(3) ral(8), "
                        + "Ancient's Pledge ral(8) ort(9) tal(7), "
                        + "Insight ral(8) tir(3) tal(7) sol(12)",
            "rw 8":     "Leaf tir(3) ral(8), "
                        + "Ancient's Pledge ral(8) ort(9) tal(7), "
                        + "Insight ral(8) tir(3) tal(7) sol(12)",
            "rw ort":   "Ancient's Pledge ral(8) ort(9) tal(7), "
                        + "Spirit tal(7) thul(10) ort(9) amn(11), "
                        + "Lore ort(9) sol(12)",
            "rw 9":     "Ancient's Pledge ral(8) ort(9) tal(7), "
                        + "Spirit tal(7) thul(10) ort(9) amn(11), "
                        + "Lore ort(9) sol(12)",
            "rw thul":  "Spirit tal(7) thul(10) ort(9) amn(11)",
            "rw 10":    "Spirit tal(7) thul(10) ort(9) amn(11)",
            "rw amn":   "Strength amn(11) tir(3), "
                        + "Spirit tal(7) thul(10) ort(9) amn(11)",
            "rw 11":    "Strength amn(11) tir(3), "
                        + "Spirit tal(7) thul(10) ort(9) amn(11)",
            "rw sol":   "Lore ort(9) sol(12), "
                        + "Insight ral(8) tir(3) tal(7) sol(12)",
            "rw 12":    "Lore ort(9) sol(12), "
                        + "Insight ral(8) tir(3) tal(7) sol(12)",
            "rw shael": "Rhyme shael(13) eth(5)",
            "rw 13":    "Rhyme shael(13) eth(5)",

            "rw steel":     "Steel tir(3) el(1)",
            "rw leaf":      "Leaf tir(3) ral(8)",
            "rw strength":  "Strength amn(11) tir(3)",
            "rw insight":   "Insight ral(8) tir(3) tal(7) sol(12)",
            "rw spirit":    "Spirit tal(7) thul(10) ort(9) amn(11)",
            "rw smoke":     "Smoke nef(4) lum(17)",
            "rw lore":      "Lore ort(9) sol(12)",
            "rw rhyme":     "Rhyme shael(13) eth(5)",
            "rw splendor":  "Splendor eth(5) lum(17)",
            "rw stealth":   "Stealth tal(7) eth(5)",

            "bp":       "bp (fcr|fhr) (ama|sin|zon|sor|pal|bar|dru|asn)",
            "bp fcr":   "bp fcr (ama|sin|zon|sor|pal|bar|dru|asn)",
            "bp fcr ama":   "fcr(frame) 0(19) 7(18) 14(17) 22(16) 32(15) 48(14) 68(13) 99(12) 152(11)",
            "bp fcr sin":   "fcr(frame) 0(16) 8(15) 16(14) 27(13) 42(12) 65(11) 102(10) 174(9)",
            "bp fcr zon":   "fcr(frame) 0(19) 7(18) 14(17) 22(16) 32(15) 48(14) 68(13) 99(12) 152(11)",
            "bp fcr sor":   "fcr(frame)\n"
                                + "ltg / chain ltg 0(19) 7(18) 15(17) 23(16) 35(15) 52(14) 78(13) 117(12) 194(11)\n"
                                + "other spells    0(13) 9(12) 20(11) 37(10) 63(9) 105(8) 200(7)",
            "bp fcr pal":   "fcr(frame) 0(15) 9(14) 18(13) 30(12) 48(11) 75(10) 125(9)",
            "bp fcr bar":   "fcr(frame) 0(13) 9(12) 20(11) 37(10) 63(9) 105(8) 200(7)",
            "bp fcr asn":   "fcr(frame) 0(16) 8(15) 16(14) 27(13) 42(12) 65(11) 102(10) 174(9)",
            "bp fcr nec":   "fcr(frame)\n"
                                + "human 0(15) 9(14) 18(13) 30(12) 48(11) 75(10) 125(9)\n"
                                + "vampr 0(23) 6(22) 11(21) 18(20) 24(19) 35(18) 48(17) 65(16) 86(15) 120(14) 180(13)",
            "bp fcr dru":   "fcr(frame)\n"
                                + "human 0(18) 4(17) 10(16) 19(15) 30(14) 46(13) 68(12) 99(11) 163(10)\n"
                                + "bear  0(16) 7(15) 15(14) 26(13) 40(12) 63(11) 99(10) 163(9)\n"
                                + "wolf  0(16) 6(15) 14(14) 26(13) 40(12) 60(11) 95(10) 157(9)",
            "bp fhr":   "bp fhr (ama|sin|zon|sor|pal|bar|dru|asn)",
            "bp fhr ama":   "fhr(frame) 0(11) 6(10) 13(9) 20(8) 32(7) 52(6) 86(5) 174(4) 600(3)",
            "bp fhr sin":   "fhr(frame) 0(9) 7(8) 15(7) 27(6) 48(5) 86(4) 200(3)",
            "bp fhr zon":   "fhr(frame) 0(11) 6(10) 13(9) 20(8) 32(7) 52(6) 86(5) 174(4) 600(3",
            "bp fhr sor":   "fhr(frame) 0(15) 5(14) 9(13) 14(12) 20(11) 30(10) 42(9) 60(8) 86(7) 142(6) 280(5)",
            "bp fhr pal":   "fhr(frame)\n"
                                + "Spears and staves 0(13) 3(12) 7(11) 13(10) 20(9) 32(8) 48(7) 75(6) 129(5) 280(4)\n"
                                + "other weapons     0(9) 7(8) 15(7) 27(6) 48(5) 86(4) 200(3)",
            "bp fhr bar":   "fhr(frame) 0(9) 7(8) 15(7) 27(6) 48(5) 86(4) 200(3)",
            "bp fhr asn":   "fhr(frame) 0(9) 7(8) 15(7) 27(6) 48(5) 86(4) 200(3)",
            "bp fhr nec":   "fhr(frame)\n"
                                + "human 0(13) 5(12) 10(11) 16(10) 26(9) 39(8) 56(7) 86(6) 152(5) 377(4)\n"
                                + "vampr 0(15) 2(14) 6(13) 10(12) 16(11) 24(10) 34(9) 48(8) 72(7) 117(6) ?(5) ?(4) ?(3) ?(2)",
            "bp fhr dru":   "fhr(frame)\n"
                                + "human 1H swinging wp 0(14) 3(13) 7(12) 13(11) 19(10) 29(9) 42(8) 63(7) 99(6) 174(5) 456(4)\n"
                                + "human other weapons  0(13) 5(12) 10(11) 16(10) 26(9) 39(8) 56(7) 86(6) 152(5) 377(4)\n"
                                + "bear  0(13) 5(12) 10(11) 16(10) 24(9) 37(8) 54(7) 86(6) 152(5) 360(4)\n"
                                + "wolf  0(7) 9(6) 20(5) 42(4) 86(3) 280(2)"
        }

    def get_info(self, cmd):
        # reorder cmd
        """

        :param cmd: the whole income whisper <from dukom> help
        :return: from, reply_mesg
        """
        ret = "Unknown command. Whisper me 'help' to see valid commands."

        parsed = self.pattern.search(cmd)
        cmds = parsed.group(1).split()
        key = " ".join(cmds)
        key = key.strip()
        if key in self.map_fullcmd2ret:
            ret = self.map_fullcmd2ret[key]
        elif len(cmds)>1:
            hpk = cmds[0] + " " + cmds[1]
            ret = self.map_fullcmd2ret[hpk] if hpk in self.map_fullcmd2ret else ret
        return ret


def main():
    D2InfoBot("play.slashdiablo.net", 6112, "dukom").connect()

main() if __name__ == '__main__' else None
