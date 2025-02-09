from tkinter import *
from tkinter import filedialog
from tkinter import messagebox
from tkinter.ttk import Progressbar
from PIL import ImageTk, Image
from utils.bag import Bag
from utils.util import get_feat_from_image, get_histogram_cluster, biggest_bbox
from utils.classifier import *
from utils.cluster import predict_kmeans
import numpy as np
import os
os.environ['OPENCV_IO_MAX_IMAGE_PIXELS']=str(2**64)
import cv2


root = Tk()
root.title('MLCD')

model_path = StringVar()
model_path.set('./models/')
input_path = StringVar()
input_path.set('Input Image Path Goes Here')
output_path = StringVar()
output_path.set('Output Path Goes Here')
run_flag = BooleanVar()
openslide_flag = BooleanVar()
openslide_flag.set(True)
try:
    import openslide
except (ImportError, OSError):
    openslide_flag.set(False)
    import warnings
    warnings.warn('Cannot support SVS format and large TIF files',
                  ImportWarning)

progressbar = Progressbar(root, orient=HORIZONTAL,
                          length=250,mode='determinate')
progressbar.place(anchor="w")


def get_input():
    global input_path, output_path
    filename = filedialog.askopenfilename(initialdir="data/",
                                          title="Select image file",
                                          filetypes=(("jpeg files", "*.jpg"),
                                                     ("tif flile", "*.tif"),
                                                     ("tiff file", "*.tiff"),
                                                     ("jpeg file", "*.jpg"),
                                                     ("png file", "*.png"),
                                                     ("svs file", "*.svs")))

    dirname = os.path.dirname(filename)
    input_path.set(filename)
    if output_path == 'Saved Image Path Goes Here':
        output_put.set(dirname)


def load_model():
    global model_path
    foldername = filedialog.askdirectory(initialdir="models/", title='Path to downloaded Models')
    model_path.set(foldername)
    #print(model_path.get())

def begin_task():
    root.update()
    model_p = model_path.get()
    input_p = input_path.get()
    if input_p == 'Input Image Path Goes Here':
        input_path.set('./data/sample.jpg')
        input_p = input_path.get()
    output_p = output_path.get()
    if output_p == 'Output Path Goes Here':
        output_path.set('./output')
        if not os.path.exists(output_path.get()):
            os.mkdir(output_path.get())
        output_p = output_path.get()
    clf_filename = os.path.join(model_p, 'clf.pkl')
    kmeans_filename = os.path.join(model_p, 'kmeans.pkl')
    # hcluster_filename = os.path.join(model_p, 'hcluster.pkl')
    if not os.path.exists(clf_filename):
        clf_filename = filedialog.askopenfilename(initialdir="./",
        title="Select Trained SVM Model File (Clf.pkl)",
        filetypes=(("Pickle File", "*.pkl"),
                   ("all files", "*.*")))
    clf=model_load(clf_filename)
    if not os.path.exists(kmeans_filename):
        kmeans_filename = filedialog.askopenfilename(initialdir="./",
        title="Select Trained K-Means Model File (kmeans.pkl)",
        filetypes=(("Pickle File", "*.pkl"),
                   ("all files", "*.*")))
    # if not os.path.exists(hcluster_filename):
    #     hcluster_filename = filedialog.askopenfilename(initialdir="./",
    #     title="Select Trained H-cluster File (hcluster.pkl)",
    #     filetypes=(("Pickle File", "*.pkl"),
    #                ("all files", "*.*")))
    loaded_kmeans = pickle.load(open(kmeans_filename, 'rb'))
    # loaded_hcluster = pickle.load(open(hcluster_filename, 'rb'))
    progressbar['value'] = 0
    percent['text'] = "{}%".format(progressbar['value'])
    root.update()

    filename, ext = os.path.splitext(input_p)
    if ext == '.SVS':
        if openslide_flag.get():
            im_os = openslide.OpenSlide(input_p)
            im_size = (im_os.dimensions[1], im_os.dimensions[0])
            if im_size[0] * im_size[1] > pow(2, 64):
                # big image
                im = None
                im_BGR = None
                print('im=None, im_BGR=None')
            else:
                im = im_os.read_region((0, 0), 0,
                                       im_os.dimensions).convert('RGB')
                im = np.array(im, dtype=uint8)
                im_BGR = cv2.cvtColor(im, cv2.COLOR_RGB2BGR)
        else:
            messagebox.showerror("Error",
                                 "Unsupported format without openslide: {}".format(ext))
            return
    else:
        im_BGR = cv2.imread(input_p)
        if im_BGR is None:
            messagebox.showerror("Error", "CV2 image read error: image must " +
                                          "have less than 2^64 pixels")
            return

        im = cv2.cvtColor(im_BGR, cv2.COLOR_BGR2RGB)
        im = np.array(im, dtype=np.uint8)
        im_size = (im.shape[0], im.shape[1])

    if im is not None:
        output = np.empty((im.shape[0], im.shape[1]))
        bags = Bag(img=im, size=3600,
                   overlap_pixel=2400, padded=True)
    elif openslide_flag.get() and im_BGR is None:  # big image
        bags = Bag(h=im_size[0],
                   w=im_size[1], size=3600,
                   overlap_pixel=2400,
                   padded=True)
        output = np.empty(im_size)
    else:
        messagebox.showerror("Error", "image read fail")
        return
    bn = os.path.basename(input_p)
    bn = os.path.splitext(bn)[0]
    feat_outname = os.path.join(os.path.dirname(input_p),
                                '{}_feat.pkl'.format(bn))
    # print(feat_outname)
    if os.path.exists(feat_outname):
        # print('precomputed')
        feat = pickle.load(open(feat_outname, 'rb'))
        precomputed = True
    else:
        feat = np.zeros([len(bags), 40])
        precomputed = False

    result = np.zeros(len(bags))
    # base = 20
    for i in range(len(bags)):
        # print('{}/{}'.format(i, len(bags)))
        # cv2.imwrite(os.path.join(output_p, '{}.jpg'. format(i)),
        #             cv2.cvtColor(bag, cv2.COLOR_RGB2BGR))
        # if (float(i) / len(bags)) * 100 > base:
        progressbar['value'] = min((float(i+1) / len(bags)) * 100, 100)
        percent['text'] = "{:.1f}%".format(progressbar['value'])
        root.update()
        # base = min(100, base + 10)
        if not precomputed:
            if bags.img is not None:
                bag = bags[i][0]
            else:
                bbox = bags.bound_box(i)
                size_r = bbox[1] - bbox[0]
                size_c = bbox[3] - bbox[2]
                top_left_x = max(bbox[2] - bags.left, 0)
                top_left_y = max(bbox[0] - bags.top, 0)
                top_left = (top_left_x, top_left_y)
                bag = im_os.read_region(top_left, 0,
                                        (size_c,
                                         size_r)).convert('RGB')
                bag = np.array(bag, dtype=np.uint8)
            try:
                feat_words = get_feat_from_image(None, False, 120, image=bag)
                cluster_words = predict_kmeans(feat_words, loaded_kmeans)
                hist_bag = get_histogram_cluster(cluster_words,
                                                 dict_size=40)
            except np.linalg.LinAlgError:
                result[i] = 0
                hist_bag = [0] * 40
                hist_bag[23] = 900
            feat[i, :] = hist_bag
            pickle.dump(feat, open(feat_outname, 'wb'))
        result[i] = model_predict(clf, [feat[i, :]])
        # print('result: {}'.format(result[i]))
        bbox = bags.bound_box(i)
        bbox[0] = max(0, min(bbox[0] - bags.top, im_size[0] - 1))
        bbox[1] = max(0, min(bbox[1] - bags.top, im_size[0] - 1))
        bbox[2] = max(0, min(bbox[2] - bags.left, im_size[1] - 1))
        bbox[3] = max(0, min(bbox[3] - bags.left, im_size[1] - 1))
        output[bbox[0]:bbox[1], bbox[2]:bbox[3]] = result[i]
        # if result[i] == 1:
        #     cv2.imwrite(os.path.join(output_p, '{}_binary.jpg'. format(i)),
        #                 np.array(output * 255, dtype=np.uint8))
        #     cv2.imwrite(os.path.join(output_p, '{}.jpg'. format(i)),
        #                 im_BGR[bbox[0]:bbox[1], bbox[2]:bbox[3]])

    # draw bounding box and save
    output *= 255
    output = np.array(output, dtype=np.uint8)
    # save image
    pickle.dump(feat, open(feat_outname, 'wb'))
    #binary_outname = os.path.join(output_p, '{}_binary.jpg'.format(bn))
    #cv2.imwrite(binary_outname, output)
    if im_BGR is None and openslide_flag.get(): 
        # if image is very large, scale
        # by 8
        output = cv2.resize(output, None,
                            fx=1/8, fy=1/8,
                            interpolation=cv2.INTER_AREA)
        im_BGR = im_os.get_thumbnail((im_os.dimensions[0]//8,
                                      im_os.dimensions[1]//8)).convert('RGB')
        im_BGR = np.array(im_BGR, dtype=np.uint8)
        im_BGR = cv2.cvtColor(im_BGR, cv2.COLOR_RGB2BGR)

    contours, hierarchy = cv2.findContours(output,
                                           cv2.RETR_TREE,
                                           cv2.CHAIN_APPROX_SIMPLE)
    final = im_BGR.copy()

    final = cv2.drawContours(final, contours, -1, (0, 0, 255), 8)
    marked_outname = os.path.join(output_p, '{}_marked.jpg'.format(bn))
    cv2.imwrite(marked_outname, final)

    # save jpeg for segmentation
    count = 0
    bboxes = []
    for cont in contours:
        x, y, w, h = cv2.boundingRect(cont)
        img = im_BGR[y:y + h, x:x + w, :]
        bboxes += [[y, y + h, x, x + w]]
        roi_outname = os.path.join(output_p, '{}_{}.jpg'.format(bn, count))
        cv2.imwrite(roi_outname, img)
    # print(bboxes)

    # # scale result and display
    # box = biggest_bbox(bboxes)
    # box[0] = max(box[0] - 20, 0)
    # box[1] = min(box[1] + 20, final.shape[0])
    # box[2] = max(box[2] - 20, 0)
    # box[3] = min(box[3] + 20, final.shape[1])
    # w = box[3] - box[2]
    # h = box[1] - box[0]

    draw_area = final.copy()

    scale_side = max(draw_area.shape[0], draw_area.shape[1])
    if scale_side > 800:
        scale_factor = float(scale_side) / 500
        final_resized = cv2.resize(draw_area, None, fx=1 / scale_factor,
                                   fy=1 / scale_factor,
                                   interpolation=cv2.INTER_AREA)
    else:
        final_resized = draw_area
    #resized_outname = os.path.join(output_p, '{}_vis.jpg'. format(bn))
    #cv2.imwrite(resized_outname, final_resized)
    display_im2 = ImageTk.PhotoImage(Image.fromarray(cv2.cvtColor(final_resized,
                                                                  cv2.COLOR_BGR2RGB)))
    im_label.configure(image=display_im2)
    im_label.image = display_im2
    root.update()


def get_outdir():
    global output_path
    if not os.path.exists("output"):
        os.mkdir("output")
    foldername = filedialog.askdirectory(initialdir="output/", title='Select Output Directory')
    output_path.set(foldername)


title = Label(root,
              text='ROIWindowClassifier',
              font=('Arial', 24),
              width=50, height=1)
title.grid(row=0, column=0, columnspan=3)

button_input = Button(root, text="Select Input Image",
                      command=get_input)
button_predict = Button(root, text="Predict",
                        command=begin_task,
                        width=40, height=2)
# button_trained_model = Button(root, text="Select Pre-trained Model Path",
                              # command=lambda: load_model())
button_output = Button(root, text="Select Output Path",
                       command=get_outdir)
# Create a white image
display_im = np.zeros((500,500,3), np.uint8) + 255

# Write some Text

font                   = cv2.FONT_HERSHEY_DUPLEX
bottomLeftCornerOfText = (160,260)
fontScale              = 0.5
fontColor              = (0, 0, 0)
lineType               = 1

display_im = cv2.putText(display_im,'Result Image Goes Here', 
    bottomLeftCornerOfText, 
    font, 
    fontScale,
    fontColor,
    lineType)

display_im = Image.fromarray(display_im)
display_im = ImageTk.PhotoImage(display_im)

# display_im = ImageTk.PhotoImage(Image.open('./test.jpg'))
im_label = Label(root, image=display_im)
percent = Label(root, text="", justify=LEFT)
# model_path_label = Label(root, textvariable=model_path)
progress_label = Label(root, text="Progress: ")
outpath_label = Label(root, textvariable=output_path)
inpath_label = Label(root, textvariable=input_path)


im_label.grid(row=7, column=0, columnspan=3, pady=15)

button_input.grid(row=2, column=0)
# button_trained_model.grid(row=1, column=0)
button_output.grid(row=3, column=0)
button_predict.grid(row=6, column=0, columnspan=3, pady=(5,0))

# model_path_label.grid(row=1, column=1)
progress_label.grid(row=4, column=0)
progressbar.grid(row=4, column=1, pady=(5, 0))
percent.grid(row=4, column=2, sticky='W')
outpath_label.grid(row=3, column=1)
inpath_label.grid(row=2, column=1)
root.mainloop()
