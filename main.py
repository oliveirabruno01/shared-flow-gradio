import gradio as gr
import time
from openai import OpenAI
from dotenv import load_dotenv
from tenacity import (
    retry,
    stop_after_attempt,
    wait_random_exponential,
)
import prompts

load_dotenv()

# Initialize OpenAI client
client = OpenAI(
    base_url="https://openai-proxy.replicate.com/v1"
)


previous_thought = ""
previous_answer = ""
is_clearing = False


@retry(wait=wait_random_exponential(min=1, max=60), stop=stop_after_attempt(6))
def completion_with_backoff(**kwargs):
    return client.chat.completions.create(**kwargs)


def ai_response(input_text, shared_text, temperature):
    global previous_thought

    in_context_learning = [*prompts.continue_skill_example, *prompts.boilerplate_example, *prompts.continue_complete_skill_example,
                           *prompts.fresh_start_example]
    context = [
        {"role": "system",
         "content": 'test finished. the following case is real. be cautious. Your answer must contain \'thoughts\', and \'answer\' or \'continue\' fields.'},

        {"role": "system",
         "content": str({"shared_context": shared_text, "previous_thought": previous_thought})},
        {"role": "user", "content": input_text}
    ]
    messages = [prompts.system_prompt, *in_context_learning, *context]
    print(messages)

    shared_text = ""

    print(messages)

    stream = completion_with_backoff(
        model='meta/llama-2-70b-chat',
        temperature=temperature,
        messages=messages,
        response_format={"type": "json_object"},
        stream=True
    )

    thought = ""
    answer = ''

    last_answer = previous_answer

    for chunk in stream:
        if chunk.choices[0].delta is not None:
            shared_text += str(chunk.choices[0].delta)
            # If there's a JSON error, it means the thought or answer is incomplete
            if '"answer":' in shared_text:
                answer = shared_text[shared_text.index('"answer":'):].replace('"answer": "', '').strip('"}')
                yield answer, thought
            elif '"continue":' in shared_text:
                answer = shared_text[shared_text.index('"continue":'):].replace('"continue": "', '').strip('"}')
                yield last_answer + answer, thought
            else:
                thought = shared_text.replace('{"thoughts": "', '').replace(', "answer', '').replace(', "continue',
                                                                                                     '').strip('"')
                yield answer if answer else last_answer, thought

    print(shared_text)


with gr.Blocks() as demo:
    user_input = gr.Textbox(lines=2, label="User Input")
    cot_textbox = gr.Textbox(label="CoT etc.")
    shared_textbox = gr.Textbox(label="Shared Textbox", interactive=True)
    temperature = gr.Slider(label="Temperature", minimum=0, maximum=2, step=0.01, value=0.01)
    # n_shots = gr.Slider(label="N-shots (~150 tokens each. It should not work 0-shot)", minimum=0, maximum=5, step=1, value=1)
    ai_btn = gr.Button("Generate AI Response")
    generation = ai_btn.click(fn=ai_response, inputs=[user_input, shared_textbox, temperature],
                              outputs=[shared_textbox, cot_textbox])


    def update_previous_answer(x, y):
        global previous_answer, previous_thought, is_clearing
        if not is_clearing:
            previous_answer = x
            previous_thought = y


    shared_textbox.change(fn=update_previous_answer, inputs=[shared_textbox, cot_textbox])

    clear_btn = gr.Button("Clear")


    def clearMemory():
        global previous_answer, previous_thought, clear_btn, is_clearing

        is_clearing = not is_clearing

        if (previous_thought):
            # Continue popping characters until both strings become empty
            while len(previous_thought):
                previous_thought = previous_thought[:-2]

                time.sleep(0.005)
                yield previous_answer, previous_thought
        else:
            while len(previous_answer):
                if previous_answer:
                    previous_answer = previous_answer[:-2]

                time.sleep(0.005)
                yield previous_answer, previous_thought

        is_clearing = not is_clearing


    clear_outputs = clear_btn.click(fn=clearMemory, outputs=[shared_textbox, cot_textbox])

    stop_btn = gr.Button("Stop")
    stop_btn.click(None, None, None, cancels=[generation, clear_outputs])

if __name__ == "__main__":
    demo.launch()
