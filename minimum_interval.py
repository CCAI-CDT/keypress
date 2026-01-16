import time

# Input function that ignores repeated inputs due to key repeat on Enter
def wait_for_enter(prompt = "", minimum_interval = 0.8):
    if not hasattr(wait_for_enter, "input_time"):
        wait_for_enter.input_time = None
    while True:
        text = input(prompt)
        previous_time = wait_for_enter.input_time
        wait_for_enter.input_time = time.time()
        if previous_time == None or len(text) > 0 or wait_for_enter.input_time - previous_time >= minimum_interval:
            return text

# Example usage
if __name__ == "__main__":
    while True:
        text = wait_for_enter()
        if len(text) == 0:
            print("You didn't write anything!")
            #break
        else:
            print("You wrote: " + text)
