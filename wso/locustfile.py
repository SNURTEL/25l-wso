from locust import HttpUser, task, between

class EchoUser(HttpUser):
    wait_time = between(1, 2)

    @task
    def echo_test(self):
        self.client.get("/echo/50000000")