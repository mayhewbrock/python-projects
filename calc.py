import tkinter as tk

root = tk.Tk()
root.title("Simple Calc")

# blue theme cause im color blind -_-
BG = '#071430'
ENTRY_BG = '#021826'
ENTRY_FG = '#E6F7FF'
NUM_BG = '#0aa3d6'
NUM_HOVER = '#12b7ee'
OP_BG = '#145ea8'
OP_HOVER = '#1b77d1'
EQ_BG = '#0f9d78'
EQ_HOVER = '#17b88f'

root.configure(bg=BG)

display = tk.Entry(root, font=('Arial', 20), justify='right',
                   bg=ENTRY_BG, fg=ENTRY_FG, insertbackground=ENTRY_FG,
                   bd=0, relief='flat')
display.grid(row=0, column=0, columnspan=4, sticky='nsew', padx=8, pady=8)

buttons = [
    '7', '8', '9', '/',
    '4', '5', '6', '*',
    '1', '2', '3', '-',
    '0', '.', '=', '+'
]

def click(val):
    if val == '=':
        expr = display.get()
        try:
            result = str(eval(expr))
            display.delete(0, tk.END)
            display.insert(0, result)
        except Exception:
            display.delete(0, tk.END)
            display.insert(0, "Error")
    else:
        display.insert(tk.END, val)

row, col = 1, 0
for btn in buttons:
    if btn in '0123456789.':
        bg, hover = NUM_BG, NUM_HOVER
    elif btn == '=':
        bg, hover = EQ_BG, EQ_HOVER
    else:
        bg, hover = OP_BG, OP_HOVER

    b = tk.Button(root, text=btn, font=('Arial', 16),
                  bg=bg, fg=ENTRY_FG, activebackground=hover,
                  activeforeground=ENTRY_FG, bd=0, relief='ridge',
                  command=lambda v=btn: click(v))
    b.grid(row=row, column=col, sticky='nsew', padx=4, pady=4)

    # hover effect
    b.bind('<Enter>', lambda e, w=b, h=hover: w.configure(bg=h))
    b.bind('<Leave>', lambda e, w=b, c=bg: w.configure(bg=c))

    col += 1
    if col > 3:
        col = 0
        row += 1

for i in range(4):
    root.columnconfigure(i, weight=1)
for i in range(5):
    root.rowconfigure(i, weight=1)

root.mainloop()
