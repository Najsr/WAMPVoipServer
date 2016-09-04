import asyncio
from asyncio import coroutine
import rsa
import time
from autobahn.wamp.types import SubscribeOptions
from autobahn.asyncio.wamp import ApplicationSession, ApplicationRunner

class Channel:
    def __init__(self, name,session):
        self.name = name
        self.users = []
        self.session = session

    def publish(self,channel,args):
        self.session.publish(channel,args)
    def findUser(self,name):
        for username in self.users:
            if(username == name):
                return username
        return -1

    def addUser(self,name):
        self.broadcastToChannelUsers(['NEWCHANUSER',self.name,name])
        self.users.append(name)
        for username in self.users:
            user = self.session.findUser(username)
            if (user != -1):
                self.publish(user.ctlchan, user.name)


    def removeUser(self,name):
        rv = self.findUser(name)
        if(rv != -1):
            user = self.session.findUser(name)
            if(user != -1):
                user.channel = ""
            self.users.remove(name)
            self.broadcastToChannelUsers(['PRUNECHANUSER', self.name, name])
        else:
            return -1

    def broadcastToChannelUsers(self,args):
        for username in self.users:
            if (username != obj):
                user = self.session.findUser(username)
                if (user != -1):
                    user.publish(user.ctlchan, args)
                else:
                    self.removeUser(username)

    def pushToChannelFromUser(self,name,message):
        obj = self.findUser(name)
        if ((obj != -1) and (message != '')):
            for username in self.users:
                if (username != obj):
                    user = self.session.findUser(username)
                    if(user != -1):
                        user.publish(user.ctlchan,[':','MESSAGE',user.name,self.name,message])
                    else:
                        self.removeUser(username)

    def __destructor__(self):
        for username in self.users:
            obj = self.session.findUser(username)
            if(obj != -1):
                obj.channel = ""



class User:
    def __init__(self, name, ctlchan, audiochan, session,pubkey):
        self.name = name
        self.ctlchan = ctlchan
        self.audiochan = audiochan
        self.session = session
        self.channel = ""
        self.role = "user"
        self.systemtime = int(time.time())
        self.pubkey = pubkey
        print("Making user with name " + self.name)

    def publish(self, channel, arguments):
        encrypted_arguments = []
        for argument in arguments:
            encrypted_arguments.append(rsa.encrypt(argument,self.pubkey))
        yield from self.session.publish(channel, encrypted_arguments)

    def ctlCallback(self, *command):
        print(command[0])
        if (command[0] == "PING"):
            self.systemtime = int(time.time())
            return
        print(command[1])
        if (command[0] == "JOINCHANNEL" and self.session.findChannel(command[1]) != -1):
            self.channel = command[1]
            self.session.findChannel(command[1]).addUser(self.name)
            self.publish(self.ctlchan, [':', 'JOINCHANNEL', command[1]])
            return
        elif(command[0] == "JOINCHANNEL"):
            self.publish(self.ctlchan, [':', 'ERR', 'CHANNOTFOUND'])
            return
        if (command[0] == "LEAVECHANNEL" and self.session.findChannel(command[1]) != -1 and (self.channel == command[1])):
            self.channel = ""
            self.session.findChannel(command[1]).removeUser(self.name)
            self.publish(self.ctlchan, [':', 'LEAVECHANNEL', command[1]])
            return
        elif(command[0] == "LEAVECHANNEL"):
            self.publish(self.ctlchan, [':', 'ERR', 'CHANNOTFOUND'])
            return
        if (command[0] == "MKCHANNEL") and (self.session.findChannel(command[1]) == -1 and command[1] != ""):
            print('Creating channel with name ' + command[1])
            self.session.channelarr.append(Channel(command[1],self.session))
            return
        elif(command[0] == "MKCHANNEL"):
            self.publish(self.ctlchan, [':', 'ERR', 'CHANALREADYEXISTS'])
            return
        if (command[0] == "RMCHANNEL") and (self.session.findChannel(command[1]) != -1 and command[1] != ""):
            print('Deleting channel with name ' + command[1])
            obj = self.session.findChannel(command[1])
            if(obj != -1):
                obj.__destructor__()
                self.session.removeChannel(obj)
            return
        elif(command[0] == "RMCHANNEL"):
            self.publish(self.ctlchan,[':','ERR','CHANNOTFOUND'])
            return
        if (command[0] == "CHANNAMES"):
            for channel in self.session.channelarr:
                self.publish(self.ctlchan, [':', 'CHANNAME', channel.name])
            return
    def __destructor__(self):
        obj = self.session.findChannel(self.channel)
        if (obj != -1):
            obj.removeUser(self.name)


class Server(ApplicationSession):
    @asyncio.coroutine
    def pruneLoop(self):
        while True:
            self.pruneUsers()
            yield from asyncio.sleep(1)

    def findChannel(self,name):
        for channel in self.channelarr:
            if (channel.name == name):
                return channel
        return -1

    def findUser(self,name):
        for user in self.userarr:
            if (user.name == name):
                return user
        return -1

    def removeUser(self,user):
        if (self.findUser(user.name) == -1):
            return -1
        self.userarr.remove(user)

    def removeChannel(self,channel):
        if (self.findChannel(channel.name) == -1):
            return -1
        self.channelarr.remove(channel)

    def removeUserFromName(self,name):
        obj = self.findUser(name)
        if (obj != -1):
            self.userarr.remove(obj)
        else:
            return -1

    def removeChannelFromName(self,name):
        obj = self.findChannel(name)
        if (obj != -1):
            self.channelarr.remove(obj)
        else:
            return -1

    def pruneUsers(self):
        for user in self.userarr:
            if((int(time.time() - user.systemtime)) > 5):
                user.__destructor__()
                removeUser(user)

    def onMainCtlEvent(self, *command):
        if(command[0] == "NICK" and (self.findUser(command[1])) == -1):
            user = User(command[1], 'com.audioctl.' + command[1], 'com.audiodata.' + command[1], self,command[2])
            self.userarr.append(user)
            yield from self.subscribe(user.ctlCallback, user.ctlchan)

    def onJoin(self, details):
        self.initialize()
        yield from self.subscribe(self.onMainCtlEvent, u"com.audioctl.main")
        yield from self.pruneLoop()
    def initialize(self):
        self.userarr = []
        self.channelarr = []
        (self.serverpubkey, self.serverprivkey) = rsa.newkeys(512)


runner = ApplicationRunner(u"ws://127.0.0.1:8080/ws", u"realm1")
runner.run(Server)