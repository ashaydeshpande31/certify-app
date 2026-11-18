"""Guess a person's display name from their email address.

Used only when someone is added with an email but no name, for example
``deshpandeashay31@gmail.com`` -> ``Ashay Deshpande``.

Rules, in order:
1. Only the part before ``@`` is used, and ``+tags`` are dropped.
2. Digits and symbols never count. ``ashay.deshpande31`` -> letters only.
3. Dots, underscores and dashes separate words.
4. A single long word is split into known first names and surnames
   (``ashaydeshpande`` -> Ashay Deshpande), and surname-first emails are put
   in first-name-first order (``deshpandeashay`` -> Ashay Deshpande).
5. If nothing sensible can be made of it, an empty string is returned and the
   mail says "Hi there," instead of showing a made-up name.

This is a best guess from a built-in list of common Indian names, so it can
be wrong for unusual names. The organiser can always edit a name.
"""

import re

FIRST_NAMES = set(
    """
aarav aarya aaditya aadi aakash aakanksha aanya aarti aashish aashna abhay abhijeet abhijit abhilash abhinav abhishek aditi aditya
ajay ajinkya akash akshay akshada akshata alok amar amey amit amol amruta amrita anand ananya anil anirudh anjali ankit ankita ankur
anmol annapurna anuj anuja anup anurag anushka apoorva apurva archana arjun arnav aryan asha ashay ashish ashok ashwin atharva atul
avani avinash ayush bhagyashree bhavesh bhavika bhushan chaitanya chetan chinmay darshan deepak deepali deepika dev devansh dhananjay
dhiraj digvijay dinesh divya durgesh eshwari faisal gaurav gauri gayatri girish gitanjali gopal govind guru hardik harsh harshad
harshal harshada hemant hrishikesh isha ishan ishwar jagdish jaya jayesh jayant jyoti kabir kajal kalyani kamlesh kanchan karan
kartik kaustubh kavita kedar ketan khushi kiran kirti komal krishna kunal kuldeep lakshmi lalit lata mahesh mahendra mandar manish
manoj mayur mayuri meera megha mihir milind mitali mohit mrunal mrunali mukesh nachiket nagesh nandini narendra neel neha nikhil
nikita nilesh nilam nirmal nishant nisha nitin nupur omkar onkar padmini pallavi pankaj parag paras pooja poonam pradeep pradnya
pragati prajakta prajwal pranav pranali pranjal prasad prashant pratik pratiksha pratima praveen preeti priya priyanka puja pushkar
rachana radhika raghav rahul raj rajan rajat rajesh rajendra rajeshwari rakesh ramesh rani ranjit rashmi ratnakar ravi ravindra
riddhi rishabh rishi ritesh ritika rohan rohit roshan rupali sachin sagar sahil sai sakshi samarth sameer samir sandeep sanika
sanjay sanjana sanket sarika sarthak saurabh sayali shailesh shailendra shamal shantanu sharad shilpa shivam shivani shraddha
shreya shreyas shridhar shrikant shripad shruti shubham shweta siddhesh siddhant siddharth sneha snehal soham somesh sonal sonali
sourabh srushti sudhir suhas sujata sumit sunil supriya suraj suresh sushant swapnil swara swati tanmay tanvi tejas tejal trupti
tushar uday umesh vaibhav vaishali vaishnavi varad varsha vedant vidya vijay vikas vikram vinay vinayak vinit vipul viraj vishal
vishwas vivek vrushali yash yashashri yashwant yogesh yogita yuvraj zoya aman ansh arun bhavna chirag disha ganesh hari jatin
kapil lokesh madhuri mangesh mansi mohan nandkishor naman naveen neeraj nimish om parth payal piyush prerna rutuja rushikesh
sandesh shashank shital snehal sonu swaraj tushar vedika vrushabh
""".split()
)

SURNAMES = set(
    """
agarwal agrawal ahire ambekar bagde bhagat bhise bhoyar bhosale bodhe borkar chaudhari chavan choudhary dabhade dahake deshmukh
deshpande deshpandey dhande dhole dhoke dongre gadge gaikwad gawande gawai ghatge ghule gupta ingole jadhav jain jaiswal joshi
kadam kale kalokhe kamble kanade karale kasar katole khandare khedkar kharat kolhe kulkarni kumar lad lokhande mahajan mahale
malviya mane meshram mishra more mundhe nagpure nagrale nikam pande pandey pardeshi patel patil pawar raut rathod sable sahu
salunke sarode shah sharma shelke shinde shirke singh sonawane sonone solanke tayade thakare thakur thakre tiwari tripathi
upadhye vaidya verma wagh wankhede wankhade waghmare wadekar yadav zade
""".split()
)

# words that are both a given name and a surname are treated as first names
_AMBIGUOUS = FIRST_NAMES & SURNAMES
_ALL_WORDS = FIRST_NAMES | SURNAMES
_MIN_PART = 3


def _segment(word):
    """Cover the whole word with known names, fewest pieces first.
    Returns a list of parts or None."""
    n = len(word)
    best = [None] * (n + 1)
    best[0] = []
    for i in range(1, n + 1):
        for j in range(max(0, i - 14), i - _MIN_PART + 1):
            part = word[j:i]
            if best[j] is not None and part in _ALL_WORDS:
                cand = best[j] + [part]
                if best[i] is None or len(cand) < len(best[i]):
                    best[i] = cand
    return best[n]


def _is_surname(w):
    return w in SURNAMES and w not in _AMBIGUOUS


def _order(parts):
    """Put first names first and known surnames last."""
    if len(parts) < 2:
        return parts
    surn = [p for p in parts if _is_surname(p)]
    if not surn:
        return parts
    rest = [p for p in parts if not _is_surname(p)]
    return rest + surn


def _split_joined(word):
    """One long word with no separators -> list of name parts."""
    if len(word) < 2 * _MIN_PART:
        return [word]
    whole = _segment(word)
    if whole:
        # one piece = the word is itself a known name, leave it alone
        return _order(whole) if len(whole) >= 2 else [word]
    # known name at one end and an unknown rest of >= 3 letters at the other
    for known in sorted(_ALL_WORDS, key=len, reverse=True):
        if len(known) < 4 or len(known) > len(word) - _MIN_PART:
            continue
        if word.startswith(known):
            return _order([known, word[len(known):]])
        if word.endswith(known):
            return _order([word[: -len(known)], known])
    return [word]


def guess_name_from_email(email):
    """Best-effort display name, or '' if the address has no usable letters."""
    local = (email or "").split("@")[0]
    local = local.split("+")[0]
    # camelCase -> separate words before lower-casing
    local = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", local)
    local = local.lower()
    tokens = [t for t in re.split(r"[^a-z]+", local) if t]
    if not tokens:
        return ""

    parts = []
    for t in tokens:
        parts.extend(_split_joined(t) if len(tokens) == 1 or len(t) >= 2 * _MIN_PART else [t])

    # "deshpande.ashay": a surname-looking first word followed by a first name
    if len(parts) >= 2 and _is_surname(parts[0]) and any(p in FIRST_NAMES for p in parts[1:]):
        parts = parts[1:] + parts[:1]

    # a lone letter is an initial, a lone leftover letter pair is noise
    clean = [p for p in parts if len(p) > 1 or len(parts) > 1]
    if not clean or all(len(p) == 1 for p in clean):
        return ""
    return " ".join(p.upper() if len(p) == 1 else p.capitalize() for p in clean)[:200]
