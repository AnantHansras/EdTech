const Section = require("../models/Section");
const SubSection = require("../models/SubSection");
const {uploadImageToCloudinary} = require(".././utils/imageUploader")
exports.createSubSection = async (req,res) => {
    try{
        //fetch data from req body
        const {sectionId,title,description} = req.body;

        //excract file/video
        const video = req.files.video;
        console.log("video :",video);
        
        //validate data
        if(!sectionId || !description || !title || !video){
            return res.status(400).json({
                success:false,
                message:"All fields are required"
            });
        }
//Introduction and basics of python
        //upload video to clodinary
        const uploadDetails = await uploadImageToCloudinary(video, process.env.FOLDER_NAME);

        //create a sub section
        const SubSectionDetails = await SubSection.create({
            title,
            timeDuration:`${uploadDetails.duration}`,
            description,
            videoUrl:uploadDetails.secure_url
        });

        //update section with subsection id
        const updatedSection = await Section.findByIdAndUpdate({_id : sectionId},{
                $push:{
                    subSection:SubSectionDetails._id
                }
            },
            {new:true}
        ).populate("subSection");

        return res.status(200).json({
            success:true,
            message:"SubSection created Successfully",
            updatedSection
        });
    }
    catch(err){
        return res.status(500).json({
            success:false,
            message:err.message
        });
    }
}

exports.updateSubSection = async (req,res) => {
    try{
        //fetch data from req body
        const {sectionId,subSectionId,title,description} = req.body;
        const subSection = await SubSection.findById(subSectionId)
  
        if (!subSection) {
          return res.status(404).json({
            success: false,
            message: "SubSection not found",
          })
        }
    
        if (title !== undefined) {
          subSection.title = title
        }
    
        if (description !== undefined) {
          subSection.description = description
        }
        if (req.files && req.files.video !== undefined) {
          const video = req.files.video
          const uploadDetails = await uploadImageToCloudinary(
            video,
            process.env.FOLDER_NAME
          )
          subSection.videoUrl = uploadDetails.secure_url
          subSection.timeDuration = `${uploadDetails.duration}`
        }
    
        await subSection.save()
        const updatedSection = await Section.findById(sectionId).populate(
            "subSection"
          )
        return res.status(200).json({
            success:true,
            message:"Subsection updated successfully",
            data: updatedSection,
        });
    }
    catch(err){
        return res.status(500).json({
            success:false,
            message:err.message
        });
    }
};

exports.deleteSubSection = async (req,res) =>{
    try{
        //fetch data parameters assuming that we are sending id in link as params
        const {subSectionId,sectionId} = req.body;
        await Section.findByIdAndUpdate(
            { _id: sectionId },
            {
              $pull: {
                subSection: subSectionId,
              },
            }
          )
        //delete section
        const subSection = await SubSection.findByIdAndDelete({ _id: subSectionId });

        if (!subSection) {
            return res
              .status(404)
              .json({ success: false, message: "SubSection not found" })
          }
          const updatedSection = await Section.findById(sectionId).populate(
            "subSection"
          )
        return res.status(200).json({
            success:true,
            message:"Sub Section deleted successfuly",
            data: updatedSection
        });
    }
    catch(err){
        return res.status(500).json({
            success:false,
            message:err.message
        });
    }
}