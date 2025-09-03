import os
import threading
import time

def log(msg, log_enabled):
    if log_enabled:
        print(f"[LOG] {msg}")

class Elevator:
    def __init__(self, id, num_floors):
        self.id = id
        self.current_floor = 0
        self.direction = 0 # 0: idle, 1: up, -1: down
        self.requests = []  # floors to stop at (from outside calls)
        self.destinations = set()  # buttons pressed inside elevator
        self.num_floors = num_floors
        self.last_stop_direction = None  # Track last direction served for request clearing
        self.hold_timer = 0  # Seconds to hold at floor
        self.last_pickup_direction = None  # Track direction of last pickup for rational destination
        self.entry_event = False  # True if someone entered this step
        self.exit_event = False   # True if someone exited this step
        self.pending_destination = None  # Store destination to add after hold
        self.awaiting_destination = False  # Set to True when a passenger enters and needs a destination

    @staticmethod
    def possible_destinations(current_floor, direction, num_floors):
        if direction == 1:
            return list(range(current_floor + 1, num_floors))
        elif direction == -1:
            return list(range(0, current_floor))
        else:
            return [f for f in range(num_floors) if f != current_floor]

    def add_request(self, floor, direction):
        if floor not in self.requests:
            self.requests.append(floor)
            self.requests.sort()

    def add_destination(self, floor):
        if 0 <= floor < self.num_floors:
            self.destinations.add(floor)

    def remove_request(self, floor):
        if floor in self.requests:
            self.requests.remove(floor)

    def remove_destination(self, floor):
        self.destinations.discard(floor)

    def next_stop(self):
        stops = set(self.requests) | self.destinations
        if not stops:
            return None
        if self.direction == 1:
            candidates = [f for f in stops if f > self.current_floor]
            if candidates:
                return min(candidates)
            candidates = [f for f in stops if f < self.current_floor]
            if candidates:
                return max(candidates)
        elif self.direction == -1:
            candidates = [f for f in stops if f < self.current_floor]
            if candidates:
                return max(candidates)
            candidates = [f for f in stops if f > self.current_floor]
            if candidates:
                return min(candidates)
        else:
            # Idle: pick nearest
            return min(stops, key=lambda f: abs(f - self.current_floor))
        return None

    def step(self, building_requests):
        self.entry_event = False
        self.exit_event = False
        if self.hold_timer > 0:
            self.hold_timer -= 1
            # After holding for pickup, add pending destination if any
            if self.hold_timer == 0 and self.awaiting_destination:
                import random
                possible_floors = Elevator.possible_destinations(
                    self.current_floor, self.last_pickup_direction, self.num_floors)
                if possible_floors:
                    dest = random.choice(possible_floors)
                    self.add_destination(dest)
                self.awaiting_destination = False
            return
        stops = set(self.requests) | self.destinations
        # Add intermediate stops for requests in the same direction
        if self.direction != 0:
            for floor in range(self.num_floors):
                if self.direction == 1 and self.current_floor < floor:
                    if 1 in building_requests.get(floor, []):
                        stops.add(floor)
                elif self.direction == -1 and self.current_floor > floor:
                    if -1 in building_requests.get(floor, []):
                        stops.add(floor)
        if stops:
            # If idle, pick nearest stop and set direction
            if self.direction == 0:
                nearest = min(stops, key=lambda f: abs(f - self.current_floor))
                if nearest > self.current_floor:
                    self.direction = 1
                elif nearest < self.current_floor:
                    self.direction = -1
                else:
                    self.direction = 0
            # Find stops in current direction
            if self.direction == 1:
                candidates = [f for f in stops if f > self.current_floor]
                if candidates:
                    next_floor = min(candidates)
                else:
                    # No more stops in this direction, check opposite
                    candidates = [f for f in stops if f < self.current_floor]
                    if candidates:
                        self.direction = -1
                        next_floor = max(candidates)
                    else:
                        self.direction = 0
                        next_floor = self.current_floor
            elif self.direction == -1:
                candidates = [f for f in stops if f < self.current_floor]
                if candidates:
                    next_floor = max(candidates)
                else:
                    candidates = [f for f in stops if f > self.current_floor]
                    if candidates:
                        self.direction = 1
                        next_floor = min(candidates)
                    else:
                        self.direction = 0
                        next_floor = self.current_floor
            else:
                next_floor = self.current_floor
            # Move elevator
            if next_floor > self.current_floor:
                self.current_floor += 1
            elif next_floor < self.current_floor:
                self.current_floor -= 1
            # Stop at floor if needed
            if self.current_floor in stops:
                # Track which direction was served for request clearing
                if self.direction != 0:
                    self.last_stop_direction = self.direction
                else:
                    self.last_stop_direction = None
                # Track entry/exit events
                if self.current_floor in self.requests:
                    self.remove_request(self.current_floor)
                    self.entry_event = True
                    self.awaiting_destination = True
                if self.current_floor in self.destinations:
                    self.remove_destination(self.current_floor)
                    self.exit_event = True
                # If stopped for a request in the same direction, clear it
                if self.direction in building_requests.get(self.current_floor, []):
                    building_requests[self.current_floor].remove(self.direction)
                # If no more stops, go idle
                if not (set(self.requests) | self.destinations):
                    self.direction = 0
                # Hold for 5 seconds when picking up a passenger
                if self.entry_event:
                    self.hold_timer = 5
                # Track direction of pickup for rational destination
                if self.entry_event:
                    self.last_pickup_direction = self.direction if self.direction != 0 else self.last_pickup_direction
        else:
            self.direction = 0
            self.last_stop_direction = None
            self.hold_timer = 0
            self.last_pickup_direction = None
            self.pending_destination = None
            self.awaiting_destination = False

class Building:
    def __init__(self, num_elevators, num_floors, log_enabled=False):
        self.num_floors = num_floors
        self.elevators = [Elevator(i, num_floors) for i in range(num_elevators)]
        self.requests = {floor: [] for floor in range(num_floors)}
        self.log_enabled = log_enabled

    def add_request(self, floor, direction):
        # Prevent up on top floor and down on bottom floor
        if (floor == 0 and direction == -1) or (floor == self.num_floors - 1 and direction == 1):
            return
        if floor >= 0 and floor < self.num_floors:
            self.requests[floor].append(direction)
            self.requests[floor] = list(set(self.requests[floor])) # Remove duplicates
            self.requests[floor].sort()
            dir_str = 'up' if direction == 1 else 'down'
            log(f"Request for elevator at floor {floor} going {dir_str}", self.log_enabled)

    def remove_request(self, floor, direction):
        if floor >= 0 and floor < self.num_floors:
            if direction in self.requests[floor]:
                self.requests[floor].remove(direction)

    def step(self):
        # Assign requests to idle elevators
        for floor, directions in list(self.requests.items()):
            for direction in list(directions):
                idle_elevators = [e for e in self.elevators if not e.requests and not e.destinations]
                if idle_elevators:
                    nearest = min(idle_elevators, key=lambda e: abs(e.current_floor - floor))
                    nearest.add_request(floor, direction)
                    # Don't remove request from building until elevator actually serves it
        # Move elevators
        for elev in self.elevators:
            prev_floor = elev.current_floor
            prev_direction = elev.direction
            elev.step(self.requests)
            # Log movement
            if elev.current_floor != prev_floor:
                log(f"Elevator {elev.id} moved from floor {prev_floor} to {elev.current_floor}", self.log_enabled)
            # Log in/out events
            if elev.entry_event:
                log(f"Passenger entered elevator {elev.id} at floor {elev.current_floor}", self.log_enabled)
            if elev.exit_event:
                log(f"Passenger exited elevator {elev.id} at floor {elev.current_floor}", self.log_enabled)
            # Remove the request in the direction just served (if any)
            if elev.last_stop_direction is not None:
                self.remove_request(elev.current_floor, elev.last_stop_direction)

    def dashboard(self):
        os.system('cls' if os.name == 'nt' else 'clear')
        print("\n--- Elevator Dashboard ---")
        for floor in reversed(range(self.num_floors)):
            line = f"Floor {floor:2d} |"
            # Show requests
            reqs = self.requests[floor]
            req_str = ""
            if 1 in reqs:
                req_str += "↑"
            else:
                req_str += " "
            if -1 in reqs:
                req_str += "↓"
            else:
                req_str += " "
            line += f" [{req_str}] |"
            # Show elevators
            for elev in self.elevators:
                if elev.current_floor == floor:
                    symbol = ''
                    if elev.hold_timer > 0:
                        symbol = f"[E{elev.id}H]"
                    else:
                        symbol = f"[E{elev.id}{'↑' if elev.direction==1 else ('↓' if elev.direction==-1 else '•')}]"
                    # Add entry/exit markers
                    if elev.entry_event and elev.exit_event:
                        symbol += "(IN/OUT)"
                    elif elev.entry_event:
                        symbol += "(IN)"
                    elif elev.exit_event:
                        symbol += "(OUT)"
                    line += f" {symbol}"
                else:
                    line += "       "
            print(line)
        # print("\nLegend: [↑]=Up request, [↓]=Down request, [E#↑]=going up, [E#↓]=down, [E#•]=idle, [E#H]=holding at floor, (IN)=person enters, (OUT)=person exits")
        # print("\n---\n")
        # Show elevator details
        for elev in self.elevators:
            dests = sorted(elev.destinations)
            next_stop = elev.next_stop()
            hold_str = f" (HOLD {elev.hold_timer}s)" if elev.hold_timer > 0 else ""
            events = []
            if elev.entry_event:
                events.append("IN")
            if elev.exit_event:
                events.append("OUT")
            event_str = f" [{' & '.join(events)}]" if events else ""
            print(f"Elevator {elev.id}: Floor {elev.current_floor} {'↑' if elev.direction==1 else ('↓' if elev.direction==-1 else '•')} | Destinations: {dests} | Next: {next_stop}{hold_str}{event_str}")
        print("\n---\n")

def random_request(building):
    floor = random.randint(0, building.num_floors - 1)
    direction = random.choice([1, -1]) # 1 for up, -1 for down
    building.add_request(floor, direction)

def simulation_loop(num_elevators=1, num_floors=10, request_interval=10, log_enabled=False):
    building = Building(num_elevators, num_floors, log_enabled=log_enabled)
    def request_thread():
        while True:
            random_request(building)
            time.sleep(request_interval)
    threading.Thread(target=request_thread, daemon=True).start()
    while True:
        building.step()
        building.dashboard()
        time.sleep(1)

if __name__ == "__main__":
    import random
    import argparse
    parser = argparse.ArgumentParser(description="Elevator Simulation")
    parser.add_argument('--num_elevators', type=int, default=1, help='Number of elevators')
    parser.add_argument('--num_floors', type=int, default=10, help='Number of floors')
    parser.add_argument('--request_interval', type=int, default=10, help='Interval between requests (seconds)')
    parser.add_argument('--log', action='store_true', help='Enable logging')
    args = parser.parse_args()
    simulation_loop(num_elevators=args.num_elevators, num_floors=args.num_floors, request_interval=args.request_interval, log_enabled=args.log)