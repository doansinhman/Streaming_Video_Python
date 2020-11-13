class VideoStream:
    def __init__(self, filename):
        """Attach to media file"""
        self.filename = filename
        try:
            self.file = open(filename, 'rb')
        except:
            raise IOError
        self.frameNum = 0

    def nextFrame(self):
        """Get next frame."""
        try:
            framelength = int(self.file.read(5))  # Get the framelength from the first 5 bits
            data = self.file.read(framelength)  # Read next frame
            self.frameNum += 1
            return data
        except:
            self.file.close()
            return None

    def frameNbr(self):
        """Get frame number."""
        return self.frameNum
