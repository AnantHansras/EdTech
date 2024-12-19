const Profile = require("../models/Profile");
const User = require("../models/User");
const {cloudinaryConnect} = require("../config/cloudinary")
const {uploadImageToCloudinary} = require("../utils/imageUploader")
const mongoose = require('mongoose');
const { findByIdAndUpdate } = require("../models/otp");
exports.updateProfile = async (req,res) => {
    //we already created null profile while creating user
    //coz we needed profile id for schema of user
    //so now we are not creating profile we are updating that profile
    try{
        //fetch data
        
        const {dateOfBirth="",about="",contactNumber,gender,firstName,lastName} = req.body;
        
        //get UserId
        console.log(req.user.id)
        const id = req.user.id;
        
        //validate data
        if(!contactNumber || !id){
            return res.status(400).json({
                success:false,
                message:"Neccessary fields are required"
            });
        }
       
        //find profile
        const userDetails = await User.findById(id);
        const profileId = userDetails.additionalDetails;
        const profileDetails = await Profile.findById(profileId);
        
        //update profile
        const updatedUserDetails = User.findByIdAndUpdate({id,firstName:firstName,lastName:lastName,image:`https://api.dicebear.com/5.x/initials/svg?seed=${firstName} ${lastName}`})
        // const updatedProfile = await Profile.findByIdAndUpdate(profileId,{dateOfBirth,about,gender,contactNumber},{new:true});
        //or we can also do
        profileDetails.dateOfBirth = dateOfBirth;
        profileDetails.about = about;
        profileDetails.gender = gender;
        profileDetails.contactNumber = contactNumber;
        await profileDetails.save();
        return res.status(200).json({
            success:true,
            message:"Profile updated successfully",
            profileDetails,
        });
    }
    catch(err){
        return res.status(500).json({
            success:false,
            message:err.message
        });
    }
}

exports.deleteAccount = async (req,res) =>{
    //we have to delete user
    
    try{
        //get userId
        const id = req.user.id;
        
        const userDetails = await User.findById(id);
        console.log(userDetails)

        if(!userDetails){
            return res.status(400).json({
                success:false,
                message:"User Not found"
            });
        }
        //delete profile
        await Profile.findByIdAndDelete({_id:userDetails.additionalDetails});
        //delete user
        await User.findByIdAndDelete(id);
        
        return res.status(200).json({
            success:true,
            message:"Account deleted succesfully"
        });
    }
    catch(err){
        return res.status(500).json({
            success:false,
            message:err.message
        });
    }
}

exports.getAllUserDetails = async (req,res) => {
    try {
        //get user id
        const id = req.user.id;

        //validate
        const userDetails = await User.findById(id).populate("additionalDetails").exec();
        if(!userDetails){
            return res.status(500).json({
                success:false,
                message:"User Not found"
            });
        }

        return res.status(500).json({
            success:true,
            message:"Fetched all user details",
            userDetails
        });
        
    } 
    catch (error) {
        return res.status(500).json({
            success:false,
            message:error.message
        })
    }

};


exports.updateDisplayPicture = async (req, res) => {
    try {
      
      const displayPicture = req.files.displayPicture
      const userId = req.user.id
      const image = await uploadImageToCloudinary(
        displayPicture,
        process.env.FOLDER_NAME,
        1000,
        1000
      )
      console.log(image)
      const updatedProfile = await User.findByIdAndUpdate(
        { _id: userId },
        { image: image.secure_url },
        { new: true }
      )
      res.send({
        success: true,
        message: `Image Updated successfully`,
        data: updatedProfile,
      })
    } catch (error) {
      return res.status(500).json({
        success: false,
        message: error.message,
      })
    }
};
  
exports.getEnrolledCourses = async (req, res) => {
  
    try {
      const userId = req.user.id
      const userDetails = await User.findOne({
        _id: userId,
      })
        .populate("courses")
        .exec()
      if (!userDetails) {
        return res.status(400).json({
          success: false,
          message: `Could not find user with id: ${userDetails}`,
        })
      }
      return res.status(200).json({
        success: true,
        data: userDetails.courses,
      })
    } catch (error) {
      return res.status(500).json({
        success: false,
        message: error.message,
      })
    }
};