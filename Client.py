from tkinter import Button, Label, W, E, N, S, messagebox
from PIL import Image, ImageTk
import socket, threading, sys, traceback, os
import time

from RtpPacket import RtpPacket

CACHE_FILE_NAME = "cache-"
CACHE_FILE_EXT = ".jpg"


class Client:
    # Define some constances
    INIT = 0
    READY = 1
    PLAYING = 2

    SETUP = 0
    PLAY = 1
    PAUSE = 2
    TEARDOWN = 3
    DESCRIBE = 4

    state = INIT  # Initial state

    def __init__(self, master, serveraddr, serverport, rtpport, filename):
        self.master = master
        self.master.protocol("WM_DELETE_WINDOW", self.handler)

        # Statistic variables
        self.statStartTime = 0
        self.statTotalPlayTime = 0
        self.statTotalByte = 0
        self.statLostPack = 0
        self.statHighestSq = 0
        self.statLostRate = 0
        self.statDataRate = 0
        self.framelength = 0
        # --------------------

        self.createWidgets()
        self.serverAddr = serveraddr
        self.serverPort = int(serverport)
        self.rtpPort = int(rtpport)
        self.fileName = filename
        self.rtspSeq = 0
        self.sessionId = 0
        self.requestSent = -1
        self.teardownAcked = 0
        self.connectToServer()
        self.frameNbr = 0

        self.SETUP_STR = 'SETUP'
        self.PLAY_STR = 'PLAY'
        self.PAUSE_STR = 'PAUSE'
        self.TEARDOWN_STR = 'TEARDOWN'
        self.DESCRIBE_STR = 'DESCRIBE'

        self.RTSP_VER = "RTSP/1.0"
        self.TRANSPORT = "RTP/UDP"

        # Remove SETUP button
        self.setupMovie()
    def createWidgets(self):
        """Build GUI."""
        # Create Setup button
        # self.setup = Button(self.master, width=20, padx=3, pady=3)
        # self.setup["text"] = "Setup"
        # self.setup["command"] = self.setupMovie
        # self.setup.grid(row=1, column=0, padx=2, pady=2)

        # Create Describe button
        self.teardown = Button(self.master, width=20, padx=3, pady=3)
        self.teardown["text"] = "Describe"
        self.teardown["command"] = self.getDescribe
        self.teardown.grid(row=1, column=0, padx=2, pady=2)

        # Create Play button
        self.start = Button(self.master, width=20, padx=3, pady=3)
        self.start["text"] = "Play"
        self.start["command"] = self.playMovie
        self.start.grid(row=1, column=1, padx=2, pady=2)

        # Create Pause button
        self.pause = Button(self.master, width=20, padx=3, pady=3)
        self.pause["text"] = "Pause"
        self.pause["command"] = self.pauseMovie
        self.pause.grid(row=1, column=2, padx=2, pady=2)

        # Create Teardown button
        self.teardown = Button(self.master, width=20, padx=3, pady=3)
        self.teardown["text"] = "Teardown"
        self.teardown["command"] = self.exitClient
        self.teardown.grid(row=1, column=3, padx=2, pady=2)

        # Create a label to display the movie
        self.label = Label(self.master, height=19)
        self.label.grid(row=0, column=0, columnspan=4, sticky=W + E + N + S, padx=5, pady=5)

        self.label1 = Label(self.master, text="Total byte received: ")
        self.label1.grid(row=2, column=1, padx=2, pady=2, sticky=E)
        self.labelTotalByte = Label(self.master)
        self.labelTotalByte.grid(row=2, column=2, padx=2, pady=2, sticky=E)

        self.label2 = Label(self.master, text="Packet lost rate: ")
        self.label2.grid(row=3, column=1, padx=2, pady=2, sticky=E)
        self.labelLostRate = Label(self.master)
        self.labelLostRate.grid(row=3, column=2, padx=2, pady=2, sticky=E)

        self.label3 = Label(self.master, text="Data rate: ")
        self.label3.grid(row=4, column=1, padx=2, pady=2, sticky=E)
        self.labelData = Label(self.master)
        self.labelData.grid(row=4, column=2, padx=2, pady=2, sticky=E)

    def setupMovie(self):
        """Setup button handler."""
        if self.state == self.INIT:
            self.sendRtspRequest(self.SETUP)

    def getDescribe(self):
        """Get infomation about playing file."""
        if self.state != self.INIT:
            self.sendRtspRequest(self.DESCRIBE)

    def exitClient(self):
        """Teardown button handler."""
        self.sendRtspRequest(self.TEARDOWN)
        self.master.destroy()  # Close the gui window
        os.remove(CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT)  # Delete the cache image from video

    def pauseMovie(self):
        """Pause button handler."""
        if self.state == self.PLAYING:
            self.sendRtspRequest(self.PAUSE)

    def playMovie(self):
        """Play button handler."""
        if self.state == self.READY:
            # Create a new thread to listen for RTP packets
            threading.Thread(target=self.listenRtp).start()
            self.playEvent = threading.Event()
            self.playEvent.clear()
            self.sendRtspRequest(self.PLAY)
            self.statStartTime = time.time()

    def listenRtp(self):
        """Listen for RTP packets."""
        while True:
            try:
                data = self.rtpSocket.recv(20480)

                # Time
                curTime = time.time()
                self.statTotalPlayTime += curTime - self.statStartTime
                self.statStartTime = curTime
                # -----------------------------

                if data:
                    rtpPacket = RtpPacket()
                    rtpPacket.decode(data)

                    currFrameNbr = rtpPacket.seqNum()
                    print("Received frame", currFrameNbr)

                    # Calculate statistics

                    # Data rate
                    self.statDataRate = 0 if self.statTotalPlayTime == 0 else (self.statTotalByte / self.statTotalPlayTime)

                    # Lost rate
                    if currFrameNbr != self.frameNbr + 1:
                        self.statLostPack += 1
                    if currFrameNbr > self.statHighestSq:
                        self.statHighestSq = currFrameNbr
                    if self.statHighestSq != 0:
                        self.statLostRate = self.statLostPack / self.statHighestSq

                    # Total data
                    self.statTotalByte += len(data)
                    # ----------------------------------------------------

                    if currFrameNbr > self.frameNbr:  # Discard the old packet
                        self.frameNbr = currFrameNbr
                        self.updateMovie(self.writeFrame(rtpPacket.getPayload()))
            except:
                # Stop listening upon requesting PAUSE or TEARDOWN
                if self.playEvent.isSet():
                    break

                # Upon receiving ACK for TEARDOWN request,
                # close the RTP socket
                if self.teardownAcked == 1:
                    try:
                        self.rtpSocket.shutdown(socket.SHUT_RDWR)
                        self.rtpSocket.close()
                    except:
                        pass
                    break

    def writeFrame(self, data):
        """Write the received frame to a temp image file. Return the image file."""
        cachename = CACHE_FILE_NAME + str(self.sessionId) + CACHE_FILE_EXT
        file = open(cachename, "wb")
        file.write(data)
        file.close()
        return cachename

    def updateMovie(self, imageFile):
        """Update the image file as video frame in the GUI."""
        photo = ImageTk.PhotoImage(Image.open(imageFile))
        self.label.configure(image=photo, height=288)
        self.label.image = photo

        self.labelTotalByte['text'] = str(self.statTotalByte) + " bytes"
        self.labelLostRate['text'] = "{:.2f}".format(self.statLostRate)
        self.labelData['text'] = "{:.2f} bytes/s".format(self.statDataRate)

    def connectToServer(self):
        """Connect to the Server. Start a new RTSP/TCP session."""
        self.rtspSocket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            self.rtspSocket.connect((self.serverAddr, self.serverPort))
        except:
            messagebox.showwarning('Connection Failed', 'Connection to \'{}\' failed.'.format(self.serverAddr))

    def sendRtspRequest(self, requestCode):
        """Send RTSP request to the server."""
        # Setup request
        if requestCode == self.SETUP and self.state == self.INIT:
            threading.Thread(target=self.recvRtspReply).start()
            self.rtspSeq = self.rtspSeq + 1
            request = "{} {} {}\nCSeq: {}\nTransport: {}; client_port: {}".format(self.SETUP_STR, self.fileName, self.RTSP_VER, self.rtspSeq, self.TRANSPORT, self.rtpPort)
            self.requestSent = self.SETUP

        elif requestCode == self.PLAY and self.state == self.READY:
            self.rtspSeq = self.rtspSeq + 1
            request = "{} {} {}\nCSeq: {}\nSession: {}".format(self.PLAY_STR, self.fileName, self.RTSP_VER, self.rtspSeq, self.sessionId)
            self.requestSent = self.PLAY

        elif requestCode == self.PAUSE and self.state == self.PLAYING:
            self.rtspSeq = self.rtspSeq + 1
            request = "{} {} {}\nCSeq: {}\nSession: {}".format(self.PAUSE_STR, self.fileName, self.RTSP_VER, self.rtspSeq, self.sessionId)
            self.requestSent = self.PAUSE

        elif requestCode == self.TEARDOWN:
            self.rtspSeq = self.rtspSeq + 1
            request = "{} {} {}\nCSeq: {}\nSession: {}".format(self.TEARDOWN_STR, self.fileName, self.RTSP_VER, self.rtspSeq, self.sessionId)
            self.requestSent = self.TEARDOWN

        elif requestCode == self.DESCRIBE:
            self.rtspSeq = self.rtspSeq + 1
            request = "{} {} {}\nCSeq: {}\nSession: {}".format(self.DESCRIBE_STR, self.fileName, self.RTSP_VER, self.rtspSeq, self.sessionId)
            self.requestSent = self.DESCRIBE

        else:
            return

        self.rtspSocket.send(request.encode())

        print('\nData sent:\n' + request)

    def recvRtspReply(self):
        """Receive RTSP reply from the server."""
        while True:
            reply = self.rtspSocket.recv(1024)

            if reply:
                self.parseRtspReply(reply)

            # Close the RTSP socket upon requesting Teardown
            if self.requestSent == self.TEARDOWN:
                self.rtspSocket.shutdown(socket.SHUT_RDWR)
                self.rtspSocket.close()
                break

    def parseRtspReply(self, data):
        """Parse the RTSP reply from the server."""
        
        lines = data.split(b'\n')
        if '404 NOT_FOUND' in data.decode(): 
            messagebox.showwarning("Warning", "File not found!")
            self.exitClient()
            
        seqNum = int(lines[1].split(b' ')[1])

        # Process only if the server reply's sequence number is the same as the request's
        if seqNum == self.rtspSeq:
            session = int(lines[2].split(b' ')[1])
            # New RTSP session ID
            if self.sessionId == 0:
                self.sessionId = session

            if self.sessionId == session and int(lines[0].split(b' ')[1]) == 200:

                if self.requestSent == self.SETUP:
                    self.state = self.READY
                    self.openRtpPort()

                elif self.requestSent == self.PLAY:
                    self.state = self.PLAYING

                elif self.requestSent == self.PAUSE:
                    self.state = self.READY
                    self.playEvent.set()

                elif self.requestSent == self.TEARDOWN:
                    self.state = self.INIT
                    self.teardownAcked = 1

                elif self.requestSent == self.DESCRIBE:
                    message = data.split(b'\r\n')
                    info = "Protocol: {}\nFile type: {}".format(message[-2][2:].decode(), message[-1][2:].decode())
                    messagebox.showinfo("Information", info)

    def openRtpPort(self):
        """Open RTP socket binded to a specified port."""
        self.rtpSocket = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

        self.rtpSocket.settimeout(0.5)

        try:
            self.state = self.READY
            self.rtpSocket.bind(('', self.rtpPort))
        except:
            messagebox.showwarning('Unable to Bind', 'Unable to bind PORT={}'.format(self.rtpPort))

    def handler(self):
        """Handler on explicitly closing the GUI window."""
        self.pauseMovie()
        if messagebox.askokcancel("Quit?", "Are you sure you want to quit?"):
            self.exitClient()
        else:  # When the user presses cancel, resume playing.
            self.playMovie()
