def load_task(tasklistfile="urllist.txt", g_log=None):
    if g_log:
        g_log.debug("load_task() start")
    url_list = []
    with open(tasklistfile, "r") as taskfile:
        for line in taskfile.readlines():
            url_line = line.strip()
            if len(url_line) > 3:
                url_list.append(url_line)
    if g_log:
        g_log.debug("load_task() end")
    return url_list