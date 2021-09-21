from channels.generic.websocket import WebsocketConsumer, AsyncJsonWebsocketConsumer
from utils.helpers import CacheManager


class RegistrationConsumer(AsyncJsonWebsocketConsumer):
    async def connect(self):
        self.reg_code = self.scope["url_route"]["kwargs"]["reg_code"]
        self.reg_session = f"registration_{self.reg_code}"
        await self.channel_layer.group_add(self.reg_session, self.channel_name)
        await self.accept()

        cached_reg_info = CacheManager.retrieve_key(f"reg_token:{self.reg_code}")
        if not cached_reg_info:
            await self.send_json({"message": "Unknown registration session "})
            return await self.close(1000)

    async def disconnect(self, close_code):
        """ Leave registration session """
        await self.channel_layer.group_discard(self.reg_session, self.channel_name)

    async def server_event_trigger(self, event):
        """ Handles general event triggering from server """
        event_data = event["event_data"]
        await self.send_json(event_data)
