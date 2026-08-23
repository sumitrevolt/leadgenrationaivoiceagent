from app.platform.scheduler import SchedulerTask

from app.integrations.postiz import PostizClient


class PostizAutoPostTask(SchedulerTask):
    name = "postiz_auto_post"
    interval = 60 * 60 * 4  # Every 4 hours

    def run(self):
        client = PostizClient()
        client.auto_post()
