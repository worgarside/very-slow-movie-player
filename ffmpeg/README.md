https://stackoverflow.com/a/67833482

> (I'm on a Mac, using Anaconda3.)
> 
> Everyone keeps saying add ffmpeg or ffprobe to your path, but to be clear this means add the executable file to your path (not the directory, not the .py file, or anything else). For some reason, even after pip installing/updating and installing/updating via homebrew both ffmpeg and ffprobe, there were no executable files on my system for either. This seems odd; I have no idea why this might be, but here's how I got it to work:
> 
> 1. Go to https://ffbinaries.com/downloads and download the zips of both ffmpeg and ffprobe for your system.
> 2. Unzip the files to get the executable files.
> 3. Move the executable files to the correct path, which for me was "usr/anaconda3/bin" (this directory primarily has executable files). As others have said, you can check your path using import os; print(os.environ['PATH']).
> 4. Manually open each of those two executable files from Finder, just so you can give permission to open the file from an unknown developer (i.e. from the ffbinaries site).
> 
> That's what finally did it for me, anyway. Hope that helps someone else with the same problem.