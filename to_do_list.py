try:
  with open("to_do.txt", "r") as f:
    to_do_list = eval(f.read())
except FileNotFoundError:

  to_do_list = []
except:
  to_do_list = []




HEADERS = ["Item", "Date", "Priority"]

def print_list():
    if not to_do_list:
        print("List is empty")
        return
    
    print("\n")
    print(f"{HEADERS[0]:<12} | {HEADERS[1]:<12} | {HEADERS[2]:<8}")
    print("-" * 45)
    
    for i, item_list in enumerate(to_do_list, 1):
        item, date, priority = item_list
        print(f"{i:2d}. {item:<12} | {date:<12} | {priority:<8}")
    
    print()


def prettyprint(item_list):
    """Print a single row, aligned like print_list()"""
    i2 = 1
    if not item_list:
        print("No items to display.")
        return
    
    print(f"{HEADERS[0]:<20} | {HEADERS[1]:<12} | {HEADERS[2]:<8}")
    print("-" * 45)
    item, date, priority = item_list
    print(f"{i2:2d}. {item:<20} | {date:<12} | {priority:<8}")
    print()
    i2 =+ 1

while True:
  question = input("""
    1: add
    2: remove
    3: view all
    4: view priority
    5: change item
    6: exit
  
  > """)
  print()
  if question == "1":
    item = input(
        "what would you like to add to the to do list?> ").strip().lower()
    for row in to_do_list:
      if item in row[0]:
        print("item is already in list.")
        break
    else:
      priority = input(
          "what priority is this?: high, medium, low> ").strip().lower()
      date = input("when is it due by? dd/mm/yyyy> ").strip().lower()
      item_list = [item, date, priority]
      to_do_list.append(item_list)
      

  elif question == "2":
    item = input("What do you want to remove from the to do list?> ").strip().lower()

    found_item = None
    for todo_item in to_do_list:
      if todo_item[0] == item:
        found_item = todo_item
        break
    if found_item:
      sure = input(
          f"Are you sure you want to permanently remove '{item}' from your to-do list? (yes/no) > "
      ).strip().lower()
      if sure == "yes":
        to_do_list.remove(found_item)
        print(f"Removed '{item}' from the to-do list.")
      elif sure == "no":
        print("Removal canceled.")
    else:
      print(f"Item '{item}' not found in the to-do list.")

  
  elif question == "3":
    if to_do_list:
      print_list()
      print()
      print()
    else:
      print("List is empty")
      

  elif question == "4":
    question4 = input("what priority do you want to view?> ").strip().lower()
    if question4 == "high":
      for row in to_do_list:
        if "high" in row:
          prettyprint(row)
    elif question4 == "medium":
      for row in to_do_list:
        if "medium" in row:
          prettyprint(row)
    elif question4 == "low":
      for row in to_do_list:
        if "low" in row:
          prettyprint(row)

          
  elif question == "5":
    changing = input("Which item do you wnat to change?> ").strip().lower()
    for row in to_do_list:
      if changing in row:
        change_to = input(f"What do you want to change '{changing} to?> ").strip().lower()
        index = row.index(changing)
        row[index] = change_to
        print(f"'{changing}' has been changed to '{change_to}'.")


  elif question == "6":
    print("exiting program!")
    break

  
  with open("to_do.txt", "w") as f:
    f.write(str(to_do_list))


