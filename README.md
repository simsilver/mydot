# mydot

This is a tool for backing up my dotfiles.

Sometimes I can't access GitHub on a new machine, so I need a tool to
back up my dotfiles as an archive. To keep the archive small, the full
git repository is not necessary. I also need to add my custom
settings. Therefore, I first shallow clone the required git
repositories, then check them out to the desired path, and finally
copy or generate my custom settings into that path. That's basically
what this tool does.

